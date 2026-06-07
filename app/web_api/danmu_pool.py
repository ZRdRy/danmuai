"""公式化弹幕库专用 API；开关与 min_on_screen 不经 PUT /api/config 全量表单。

路由（由 ``app.web_api.routes`` 注册）：
- ``GET /api/danmu-pool/status``：内置/自定义开关 + pool size。
- ``POST /api/danmu-pool/custom``：追加自定义句（去重 + 截断），上限 500。
- ``PUT /api/danmu-pool/setting``：写 ``danmu_pool_enabled`` / ``danmu_pool_use_custom`` /
  ``min_on_screen``；**不**走 ``PUT /api/config`` 全量表单。
- ``DELETE /api/danmu-pool/custom/{id}``：删除自定义句。

设计约束：开关与自定义句的写入**只**走本模块专用路由，避免污染 ``PUT /api/config``；
否则 ``ConfigService.WEB_CONFIG_KEYS`` 白名单与 ``apply_web_config_payload`` 校验会
误把这些字段当成未知键剔除。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.danmu_engine import resolve_danmu_max_chars
from app.danmu_pool import (
    any_danmu_pool_source_enabled,
    custom_pool_size,
    danmu_pool_enabled_from_config,
    danmu_pool_use_custom_from_config,
    find_duplicates_with_builtin,
    pool_size,
)

if TYPE_CHECKING:
    from main import DanmuApp

CUSTOM_POOL_MAX = 500
APPEND_BATCH_MAX = 100
MIN_ON_SCREEN_MAX = 50

_SKIP_REASON_TOO_LONG = "too_long"
_SKIP_REASON_DUPLICATE = "duplicate"
_SKIP_REASON_EMPTY = "empty"
_SKIP_REASON_UNSAFE = "unsafe"
_SKIP_REASON_LIMIT = "limit_reached"
_SKIP_REASON_MERGED_DUPLICATE = "merged_duplicate"  # W-DANMU-POOL-002: 与内置池字面重复


def _overlay_safe(text: str, *, max_chars: int) -> bool:
    try:
        from scripts.extract_danmu_pool import is_overlay_safe
    except ImportError:
        return True
    return is_overlay_safe(text, max_chars=max_chars)


def get_meta(app: "DanmuApp") -> dict[str, Any]:
    config = app.config
    return {
        "builtin_enabled": danmu_pool_enabled_from_config(config),
        "custom_enabled": danmu_pool_use_custom_from_config(config),
        "min_on_screen": config.get_int("min_on_screen", 5),
        "builtin_count": pool_size(),
        "custom_count": custom_pool_size(config),
        "effective_pool_enabled": any_danmu_pool_source_enabled(config),
    }


def save_settings(app: "DanmuApp", payload: dict[str, Any]) -> dict[str, Any]:
    items: dict[str, str] = {}
    if "builtin_enabled" in payload:
        items["danmu_pool_enabled"] = "1" if payload.get("builtin_enabled") else "0"
    if "custom_enabled" in payload:
        items["danmu_pool_use_custom"] = "1" if payload.get("custom_enabled") else "0"
    if "min_on_screen" in payload:
        try:
            min_n = int(payload.get("min_on_screen", 5))
        except (TypeError, ValueError):
            min_n = 5
        items["min_on_screen"] = str(max(0, min(min_n, MIN_ON_SCREEN_MAX)))
    if items:
        app.config.set_batch(items)
        app.config_changed.emit()
    return {"ok": True}


def list_custom(app: "DanmuApp") -> dict[str, Any]:
    return {"items": app.config.get_custom_danmu_pool()}


def _parse_incoming_lines(payload: dict[str, Any]) -> list[str]:
    if isinstance(payload.get("items"), list):
        raw_lines = [str(item) for item in payload["items"]]
    else:
        text = str(payload.get("text") or "")
        raw_lines = text.splitlines()
    return raw_lines


def append_custom(app: "DanmuApp", payload: dict[str, Any]) -> dict[str, Any]:
    raw_lines = _parse_incoming_lines(payload)
    if len(raw_lines) > APPEND_BATCH_MAX:
        raise ValueError(f"单次最多追加 {APPEND_BATCH_MAX} 条")

    config = app.config
    existing = list(config.get_custom_danmu_pool())
    existing_set = set(existing)
    max_len = resolve_danmu_max_chars(config)
    # W-DANMU-POOL-002: 一次性预算与内置池的交集，循环内 O(1) 判定
    builtin_dup_set = find_duplicates_with_builtin(raw_lines)

    added: list[str] = []
    skipped_items: list[dict[str, str]] = []

    for raw in raw_lines:
        text = str(raw).strip()
        if not text:
            skipped_items.append({"text": raw, "reason": _SKIP_REASON_EMPTY})
            continue
        if text in existing_set:
            skipped_items.append({"text": text, "reason": _SKIP_REASON_DUPLICATE})
            continue
        if text in builtin_dup_set:  # W-DANMU-POOL-002
            skipped_items.append({"text": text, "reason": _SKIP_REASON_MERGED_DUPLICATE})
            continue
        if len(text) > max_len:
            skipped_items.append({"text": text, "reason": _SKIP_REASON_TOO_LONG})
            continue
        if not _overlay_safe(text, max_chars=max_len):
            skipped_items.append({"text": text, "reason": _SKIP_REASON_UNSAFE})
            continue
        if len(existing) + len(added) >= CUSTOM_POOL_MAX:
            skipped_items.append({"text": text, "reason": _SKIP_REASON_LIMIT})
            continue
        added.append(text)
        existing_set.add(text)

    if added:
        merged = existing + added
        config.set_custom_danmu_pool(merged)
        app.config_changed.emit()

    return {
        "added": len(added),
        "skipped": len(skipped_items),
        "items": config.get_custom_danmu_pool(),
        "skipped_items": skipped_items,
    }


def delete_custom(app: "DanmuApp", payload: dict[str, Any]) -> dict[str, Any]:
    texts = payload.get("texts")
    if not isinstance(texts, list) or not texts:
        raise ValueError("请提供要删除的弹幕句")

    remove = {str(text).strip() for text in texts if str(text).strip()}
    existing = app.config.get_custom_danmu_pool()
    kept = [line for line in existing if line not in remove]
    removed = len(existing) - len(kept)
    if removed:
        app.config.set_custom_danmu_pool(kept)
        app.config_changed.emit()
    return {"removed": removed, "items": app.config.get_custom_danmu_pool()}
