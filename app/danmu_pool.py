"""公式化弹幕库：内置 JSON + SQLite 自定义句；供 on-screen 补足与 normalize_reply_batch 填充。

开关与 min_on_screen 经 /api/danmu-pool/* 写入（见 web_api/danmu_pool.py），不在 PUT /api/config 全量表单内。
任一库开启且 min_on_screen>0 时，main._maybe_pool_topup 从合并池抽样补足同屏密度。
"""

from __future__ import annotations

import json
import random
from functools import lru_cache

from app.bundle_paths import resource_path

_DATA_DIR = resource_path("data")
_POOL_PATH = _DATA_DIR / "danmu_pool_zh.json"
_BOOTSTRAP_PATH = _DATA_DIR / "danmu_pool_zh_bootstrap.txt"
_POOL_VERSION = 1


def danmu_pool_enabled_from_config(config) -> bool:
    """True when built-in formula pool is enabled (default on per CONFIG_DEFAULTS)."""
    raw = config.get("danmu_pool_enabled", "")
    if raw in ("", None):
        return False
    return str(raw).strip() != "0"


def danmu_pool_use_custom_from_config(config) -> bool:
    """True when custom formula pool is enabled (default off if unset)."""
    raw = config.get("danmu_pool_use_custom", "")
    if raw in ("", None):
        return False
    return str(raw).strip() != "0"


def any_danmu_pool_source_enabled(config) -> bool:
    """True when at least one formula pool source (builtin or custom) is enabled."""
    if config is None:
        return True
    return danmu_pool_enabled_from_config(config) or danmu_pool_use_custom_from_config(config)


def pool_enabled(config) -> bool:
    """Respect any pool source; None config keeps legacy test behavior (enabled)."""
    if config is None:
        return True
    return any_danmu_pool_source_enabled(config)


def effective_min_on_screen(config) -> int:
    """Formula top-up target; 0 when no pool source is enabled."""
    if not any_danmu_pool_source_enabled(config):
        return 0
    return max(0, config.get_int("min_on_screen", 5))


def load_custom_danmu_pool(config) -> list[str]:
    if config is None or not danmu_pool_use_custom_from_config(config):
        return []
    getter = getattr(config, "get_custom_danmu_pool", None)
    if callable(getter):
        items = getter()
    else:
        raw = config.get_json("custom_danmu_pool", []) if hasattr(config, "get_json") else []
        items = raw if isinstance(raw, list) else []
    return _dedupe_lines(str(item) for item in items)


def load_danmu_pool_for_config(config) -> list[str]:
    # None config: legacy tests / callers expect built-in pool only.
    if config is None:
        return load_danmu_pool()
    if not pool_enabled(config):
        return []
    items: list[str] = []
    if danmu_pool_enabled_from_config(config):
        items.extend(load_danmu_pool())
    if danmu_pool_use_custom_from_config(config):
        items.extend(load_custom_danmu_pool(config))
    return _dedupe_lines(items)


def find_duplicates_with_builtin(items) -> set[str]:
    """Return the subset of ``items`` that already exist in the built-in pool.

    Used by the Web API to surface ``merged_duplicate`` rejections instead of
    silently dropping the entry. W-DANMU-POOL-002: kept as a helper so callers
    can compute the set once before iterating; does not mutate state.
    """
    builtin = set(load_danmu_pool())
    return {str(item).strip() for item in items if str(item).strip() in builtin}


def sample_danmu_for_config(
    config,
    count: int,
    *,
    rng: random.Random | None = None,
) -> list[str]:
    if not pool_enabled(config) or count <= 0:
        return []
    pool = load_danmu_pool_for_config(config)
    if not pool:
        return []
    rng = rng or random
    if count >= len(pool):
        return rng.sample(pool, len(pool))
    return rng.sample(pool, count)


def _dedupe_lines(lines) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


@lru_cache(maxsize=1)
def load_danmu_pool() -> list[str]:
    if _POOL_PATH.is_file():
        try:
            payload = json.loads(_POOL_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list) and items:
                return _dedupe_lines(items)
        elif isinstance(payload, list) and payload:
            return _dedupe_lines(payload)

    if _BOOTSTRAP_PATH.is_file():
        try:
            lines = _BOOTSTRAP_PATH.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        if lines:
            return _dedupe_lines(lines)
    return []


def pool_size() -> int:
    return len(load_danmu_pool())


def custom_pool_size(config) -> int:
    return len(load_custom_danmu_pool(config))


def sample_danmu(count: int, *, rng: random.Random | None = None) -> list[str]:
    pool = load_danmu_pool()
    if not pool or count <= 0:
        return []
    rng = rng or random
    if count >= len(pool):
        return rng.sample(pool, len(pool))
    return rng.sample(pool, count)


def pool_metadata() -> dict:
    if not _POOL_PATH.is_file():
        return {"version": _POOL_VERSION, "count": 0, "path": str(_POOL_PATH)}
    try:
        payload = json.loads(_POOL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "version": payload.get("version", _POOL_VERSION),
        "count": pool_size(),
        "target": payload.get("target"),
        "sources": payload.get("sources"),
        "path": str(_POOL_PATH),
    }


def maybe_pool_topup(engine, config, scene_generation: int) -> int:
    """从合并池抽样补足同屏密度。

    Returns the number of items actually added.
    """
    if not engine.running:
        return 0
    if not any_danmu_pool_source_enabled(config):
        return 0
    # W-DANMU-POOL-003: 用户配了 danmu_pending_entry_cap 时，避免入口区被池句占满
    # entry_zone_overloaded 仅在 pending_cap > 0 时返回 True（danmu_engine.py:395-399）
    # 用 getattr 兜底：FakeEngine 等测试桩未实现此方法时按"未过载"处理
    if getattr(engine, "entry_zone_overloaded", lambda: False)():
        return 0
    deficit = engine.deficit_below_min()
    if deficit <= 0:
        return 0
    limit = min(deficit, 8)
    texts = sample_danmu_for_config(config, limit)
    if not texts:
        return 0
    added = 0
    for text in texts:
        if added >= limit:
            break
        item = engine.add_text(
            text,
            persona="",
            batch_id=0,
            scene_generation=scene_generation,
            skip_dedup=True,  # W-DANMU-POOL-001: 合并池自身已 _dedupe_lines，不再走 deque(30) 窗口
        )
        if item:
            added += 1
    return added
