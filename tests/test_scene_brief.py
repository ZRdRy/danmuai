"""Scene brief store and main integration tests."""

import time

from app.memory.types import scene_memory_tick_multiplier, snap_scene_memory_interval_sec
from app.reply_queue import QueuedReply
from app.scene_memory import SceneBriefStore, append_blocks_to_user_pt
from main import DanmuApp

from tests.conftest import bind_minimal_danmu_app
from tests.fakes import FakeConfig


def _store_with_bullets(*phrases: str) -> SceneBriefStore:
    store = SceneBriefStore()
    for i, phrase in enumerate(phrases):
        store.record_displayed_bullet(phrase, window=10, angle=f"scene_{i}")
    return store


def test_scene_memory_disabled_does_not_append_brief():
    cfg = FakeConfig()
    cfg.get = lambda key, default="": {
        "scene_memory_enabled": "0",
        "prompt_dedup_enabled": "0",
    }.get(key, default)
    cfg.get_int = lambda key, default=0: default

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg, _scene_generation=0)
    store = _store_with_bullets("旧弹幕")
    store.set_brief("上一帧在打团")
    app._scene_memory = store
    base = "请基于这张截图生成弹幕："
    assert app._append_scene_context_to_user_pt(base) == base


def test_scene_memory_enabled_appends_brief_block():
    cfg = FakeConfig()
    cfg.get = lambda key, default="": {
        "scene_memory_enabled": "1",
        "prompt_dedup_enabled": "0",
    }.get(key, default)
    cfg.get_int = lambda key, default=0: default

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg, _scene_generation=0)
    store = SceneBriefStore()
    store.set_brief("主播在打团")
    app._scene_memory = store
    result = app._append_scene_context_to_user_pt("请生成弹幕：")
    assert "【当前场景】" in result
    assert "主播在打团" in result
    assert "若与当前截图冲突" in result
    assert "【最近弹幕去重】" not in result


def test_prompt_dedup_enabled_appends_dedup_only():
    cfg = FakeConfig()
    cfg.get = lambda key, default="": {
        "scene_memory_enabled": "0",
        "prompt_dedup_enabled": "1",
    }.get(key, default)
    cfg.get_int = lambda key, default=0: default

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg, _scene_generation=0)
    app._scene_memory = _store_with_bullets("延续语境")
    result = app._append_scene_context_to_user_pt("请生成弹幕：")
    assert "【最近弹幕去重】" in result
    assert "【当前场景】" not in result


def test_bullets_do_not_grow_beyond_window():
    store = SceneBriefStore()
    for i in range(25):
        store.record_displayed_bullet(f"弹幕{i}", window=10, angle=f"scene_{i % 3}")
    assert len(store.dedup.recent_bullets) == 10


def test_record_prompt_dedup_skips_when_disabled():
    cfg = FakeConfig()
    cfg.get = lambda key, default="": {
        "scene_memory_enabled": "1",
        "prompt_dedup_enabled": "0",
    }.get(key, default)
    cfg.get_int = lambda key, default=0: default

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg)
    app._scene_memory = SceneBriefStore()
    app._record_prompt_dedup_display = DanmuApp._record_prompt_dedup_display.__get__(app, DanmuApp)
    queued = QueuedReply(
        persona_id="p",
        batch_index=0,
        content_index=0,
        content="有效弹幕",
        screenshot_round=1,
        screenshot_id=1,
        captured_at=time.monotonic(),
        scene_generation=0,
        batch_id=1,
        source="ai",
    )
    app._record_prompt_dedup_display(queued)
    assert app._scene_memory.dedup.recent_bullets == []


def test_record_prompt_dedup_accepts_mic_source():
    cfg = FakeConfig()
    cfg.get = lambda key, default="": {"prompt_dedup_enabled": "1"}.get(key, default)
    cfg.get_int = lambda key, default=0: default

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg)
    app._scene_memory = SceneBriefStore()
    app._record_prompt_dedup_display = DanmuApp._record_prompt_dedup_display.__get__(app, DanmuApp)
    queued = QueuedReply(
        persona_id="p",
        batch_index=0,
        content_index=0,
        content="mic 弹幕",
        screenshot_round=1,
        screenshot_id=1,
        captured_at=time.monotonic(),
        scene_generation=0,
        batch_id=1,
        source="mic",
    )
    app._record_prompt_dedup_display(queued)
    assert len(app._scene_memory.dedup.recent_bullets) == 1


def test_snap_scene_memory_interval_sec_to_recognition_multiple():
    assert snap_scene_memory_interval_sec(7, 5) == 10
    assert snap_scene_memory_interval_sec(5, 5) == 5
    assert snap_scene_memory_interval_sec(99, 5) == 60


def test_scene_memory_update_due_follows_multiplier():
    cfg = FakeConfig(
        {
            "scene_memory_enabled": "1",
            "normal_recognition_interval_sec": "5",
            "scene_memory_interval_sec": "10",
        }
    )
    assert scene_memory_tick_multiplier(cfg) == 2

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg)
    due = DanmuApp._scene_memory_update_due.__get__(app, DanmuApp)
    assert due(2) is True
    assert due(3) is False
    assert due(4) is True


def test_scene_memory_still_injects_between_refresh_ticks():
    cfg = FakeConfig(
        {
            "scene_memory_enabled": "1",
            "prompt_dedup_enabled": "0",
            "normal_recognition_interval_sec": "5",
            "scene_memory_interval_sec": "10",
        }
    )
    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=cfg)
    store = SceneBriefStore()
    store.set_brief("旧场景")
    app._scene_memory = store
    due = DanmuApp._scene_memory_update_due.__get__(app, DanmuApp)
    assert due(3) is False
    result = app._append_scene_context_to_user_pt("请生成弹幕：")
    assert "旧场景" in result


def test_append_blocks_to_user_pt_joins_sections():
    result = append_blocks_to_user_pt(
        "基础提示",
        "【当前场景】\n团战",
        "【最近弹幕去重】\n最近上屏：A",
    )
    assert result.startswith("基础提示")
    assert "【当前场景】" in result
    assert "【最近弹幕去重】" in result
