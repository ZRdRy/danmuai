"""Danmu pool loader tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
POOL_JSON = REPO_ROOT / "data" / "danmu_pool_zh.json"
BOOTSTRAP_TXT = REPO_ROOT / "data" / "danmu_pool_zh_bootstrap.txt"


def test_bootstrap_txt_has_400_lines():
    assert BOOTSTRAP_TXT.is_file(), "missing data/danmu_pool_zh_bootstrap.txt"
    lines = [ln.strip() for ln in BOOTSTRAP_TXT.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 400
    # Formula #251–253 are single-char (顶/行/顺); overlay allows ≤15.
    assert all(1 <= len(ln) <= 15 for ln in lines)


def test_danmu_pool_enabled_from_config(tmp_path):
    from app.config_store import ConfigStore
    from app.danmu_pool import danmu_pool_enabled_from_config

    store = ConfigStore(db_path=tmp_path / "pool_flag.db")
    assert danmu_pool_enabled_from_config(store) is True
    store.set("danmu_pool_enabled", "1")
    assert danmu_pool_enabled_from_config(store) is True
    store.set("danmu_pool_enabled", "0")
    assert danmu_pool_enabled_from_config(store) is False


def test_danmu_pool_use_custom_from_config(tmp_path):
    from app.config_store import ConfigStore
    from app.danmu_pool import danmu_pool_use_custom_from_config

    store = ConfigStore(db_path=tmp_path / "custom_flag.db")
    assert danmu_pool_use_custom_from_config(store) is False
    store.set("danmu_pool_use_custom", "1")
    assert danmu_pool_use_custom_from_config(store) is True


def test_any_danmu_pool_source_enabled(tmp_path):
    from app.config_store import ConfigStore
    from app.danmu_pool import any_danmu_pool_source_enabled

    store = ConfigStore(db_path=tmp_path / "any_source.db")
    assert any_danmu_pool_source_enabled(store) is True
    store.set("danmu_pool_enabled", "1")
    assert any_danmu_pool_source_enabled(store) is True
    store.set("danmu_pool_enabled", "0")
    store.set("danmu_pool_use_custom", "1")
    assert any_danmu_pool_source_enabled(store) is True


def test_pool_for_config_disabled_returns_empty(tmp_path):
    from app.config_store import ConfigStore
    from app.danmu_pool import (
        load_danmu_pool,
        load_danmu_pool_for_config,
        sample_danmu_for_config,
    )

    store = ConfigStore(db_path=tmp_path / "pool_gate.db")
    store.set("danmu_pool_enabled", "0")
    store.set("danmu_pool_use_custom", "0")
    assert load_danmu_pool_for_config(store) == []
    assert sample_danmu_for_config(store, 5) == []
    if load_danmu_pool():
        store.set("danmu_pool_enabled", "1")
        assert load_danmu_pool_for_config(store)
        assert sample_danmu_for_config(store, 3)


def test_custom_only_pool_for_config(tmp_path):
    from app.config_store import ConfigStore
    from app.danmu_pool import (
        effective_min_on_screen,
        load_danmu_pool_for_config,
        sample_danmu_for_config,
    )

    store = ConfigStore(db_path=tmp_path / "custom_only.db")
    store.set("danmu_pool_enabled", "0")
    store.set("danmu_pool_use_custom", "1")
    store.set_custom_danmu_pool(["自定义A", "自定义B", "自定义C"])
    assert load_danmu_pool_for_config(store) == ["自定义A", "自定义B", "自定义C"]
    picked = sample_danmu_for_config(store, 2)
    assert len(picked) == 2
    assert all(p in store.get_custom_danmu_pool() for p in picked)
    store.set("min_on_screen", "5")
    assert effective_min_on_screen(store) == 5


def test_load_danmu_pool_has_merged_bootstrap():
    from app.danmu_pool import load_danmu_pool

    pool = load_danmu_pool()
    if POOL_JSON.is_file():
        assert len(pool) >= 1300
        assert "懂了" in pool and "这操作有点秀" in pool
    else:
        assert len(pool) >= 400


@pytest.mark.skipif(not POOL_JSON.is_file(), reason="run scripts/extract_danmu_pool.py first")
def test_extracted_pool_has_corpus_and_bootstrap():
    data = json.loads(POOL_JSON.read_text(encoding="utf-8"))
    assert data["count"] >= 1300
    items = data["items"]
    assert len(items) == data["count"]
    assert items[0] == "这操作有点秀"
    assert data.get("bootstrap_count", 0) >= 400
    assert all(1 <= len(str(t)) <= 15 for t in items[:50])


def test_pool_items_pass_overlay_safety_filter():
    from scripts.extract_danmu_pool import is_overlay_safe

    if not POOL_JSON.is_file():
        pytest.skip("missing pool json")
    items = json.loads(POOL_JSON.read_text(encoding="utf-8")).get("items", [])
    bad = [t for t in items if not is_overlay_safe(str(t))]
    assert not bad, f"sensitive or unsafe pool lines: {bad[:10]}"


def test_sample_danmu_unique():
    from app.danmu_pool import load_danmu_pool, sample_danmu

    pool = load_danmu_pool()
    assert pool
    picked = sample_danmu(20)
    assert len(picked) == 20
    assert len(set(picked)) == 20


def test_pool_topup_returns_0_when_entry_zone_overloaded(qapp, workspace_tmp):
    """W-DANMU-POOL-003: 用户配了 danmu_pending_entry_cap 时，入口区满则池补足早返 0。"""
    from unittest.mock import MagicMock

    from app.config_store import ConfigStore
    from app.danmu_engine import DanmuEngine
    from app.danmu_pool import maybe_pool_topup

    store = ConfigStore(db_path=workspace_tmp / "pool_topup_overload.db")
    store.set("danmu_pool_use_custom", "1")
    store.set("min_on_screen", "5")
    store.set_custom_danmu_pool(["句1", "句2", "句3", "句4", "句5", "句6"])

    engine = DanmuEngine(store)
    engine.set_screen_width(1920.0)
    engine.set_screen_height(1080.0)
    engine.reload_tracks()
    engine.running = True
    # 模拟入口过载
    engine.entry_zone_overloaded = MagicMock(return_value=True)
    add_text_calls: list[str] = []
    original_add_text = engine.add_text
    engine.add_text = MagicMock(side_effect=lambda *a, **kw: add_text_calls.append(a[0]) or original_add_text(*a, **kw))

    added = maybe_pool_topup(engine, store, scene_generation=0)

    assert added == 0
    assert engine.add_text.call_count == 0
    assert add_text_calls == []


def test_pool_topup_skips_recent_dedup_window(qapp, workspace_tmp):
    """W-DANMU-POOL-001: 池补足 add_text(skip_dedup=True) 不受 deque(30) 窗口误伤。

    模拟"自定义句与最近 30 条历史字面相同"场景：先 engine.add_text 30 条占满窗口，
    再写入 custom_danmu_pool["撞车句"]，调 maybe_pool_topup，断言实际入轨。
    """
    from app.config_store import ConfigStore
    from app.danmu_engine import DanmuEngine
    from app.danmu_pool import maybe_pool_topup

    store = ConfigStore(db_path=workspace_tmp / "pool_topup_skip_dedup.db")
    store.set("danmu_pool_use_custom", "1")
    store.set("danmu_pool_enabled", "0")
    store.set("min_on_screen", "3")
    store.set_custom_danmu_pool(["撞车句"])

    engine = DanmuEngine(store)
    engine.set_screen_width(1920.0)
    engine.set_screen_height(1080.0)
    engine.reload_tracks()
    engine.running = True
    engine.recent.clear()
    engine.recent_exact_set.clear()

    # 预占 deque(30)：让"撞车句"在 recent_exact_set 中
    for i in range(30):
        engine._remember_content("history-" + str(i))
    engine._remember_content("撞车句")
    assert "撞车句" in engine.recent_exact_set

    # 取 min_on_screen=3，屏空 → deficit=3 → 抽样最多 3 条 → 但合并池只有 1 条
    added = maybe_pool_topup(engine, store, scene_generation=0)

    assert added == 1
    all_texts = [
        item.content
        for track in engine.tracks
        for item in track.items
    ]
    assert "撞车句" in all_texts

