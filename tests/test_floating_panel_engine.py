"""W-FP-V3-002：FloatingPanelEngine 连续上滚模型测试。"""
from __future__ import annotations

from app.config_store import ConfigStore
from app.floating_panel_engine import FloatingPanelEngine


def _engine(tmp_path, **overrides) -> FloatingPanelEngine:
    store = ConfigStore(db_path=tmp_path / "fp_engine.db")
    for key, value in overrides.items():
        store.set(key, str(value))
    engine = FloatingPanelEngine(store)
    engine.set_panel_height(400.0)
    return engine


def test_add_text_returns_item(workspace_tmp):
    engine = _engine(workspace_tmp)
    item = engine.add_text("hello", item_height=32.0, now=0.0)
    assert item is not None
    assert item.content == "hello"
    assert engine.visible_count() == 1


def test_new_item_starts_at_bottom(workspace_tmp):
    engine = _engine(workspace_tmp)
    item = engine.add_text("bottom", item_height=40.0, now=0.0)
    assert item is not None
    assert item.current_y == 400.0


def test_second_item_also_starts_from_bottom_baseline(workspace_tmp):
    engine = _engine(workspace_tmp)
    first = engine.add_text("one", item_height=40.0, now=0.0)
    second = engine.add_text("two", item_height=40.0, now=0.1)
    assert first is not None and second is not None
    assert first.current_y == 400.0
    assert second.current_y == 400.0


def test_duplicate_rejected(workspace_tmp):
    engine = _engine(workspace_tmp)
    assert engine.add_text("dup", item_height=32.0) is not None
    assert engine.add_text("dup", item_height=32.0) is None


def test_max_items_forces_oldest_exit(workspace_tmp):
    engine = _engine(workspace_tmp, floating_panel_max_items="3")
    for i in range(4):
        engine.add_text(f"line-{i}", item_height=30.0, now=0.0)
    assert engine.visible_count() == 3
    assert engine.visible_items()[-1].content == "line-3"
    assert engine.visible_items()[0].content != "line-0"


def test_engine_uses_floating_panel_speed_for_pixels_per_second(workspace_tmp):
    engine = _engine(workspace_tmp, floating_panel_speed="3.0")
    assert engine.pixels_per_second == 360.0


def test_items_scroll_upward_until_offscreen_then_removed(workspace_tmp):
    engine = _engine(workspace_tmp)
    item = engine.add_text("scroll-up", item_height=40.0, now=0.0)
    assert item is not None
    engine.update(1.0, now=1.0)
    assert item.current_y == 382.0
    for _ in range(30):
        engine.update(0.1, now=99.0)
        if engine.visible_count() == 0:
            break
    assert engine.visible_count() == 0


def test_engine_does_not_use_hold_or_lifetime_exit_semantics(workspace_tmp):
    engine = _engine(workspace_tmp, floating_panel_lifetime_sec="1")
    item = engine.add_text("no-hold", item_height=40.0, now=0.0)
    assert item is not None
    engine.update(0.5, now=10.0)
    assert engine.visible_count() == 1
    assert item.current_y == 382.0


def test_slower_speed_produces_smaller_delta_than_faster_speed(workspace_tmp):
    slow = _engine(workspace_tmp, floating_panel_speed="0.5")
    fast = _engine(workspace_tmp, floating_panel_speed="3.0")
    slow_item = slow.add_text("slow", item_height=40.0, now=0.0)
    fast_item = fast.add_text("fast", item_height=40.0, now=0.0)
    assert slow_item is not None and fast_item is not None
    slow.update(1.0, now=1.0)
    fast.update(1.0, now=1.0)
    slow_delta = 400.0 - slow_item.current_y
    fast_delta = 400.0 - fast_item.current_y
    assert slow_delta < fast_delta


def test_clear_resets_state(workspace_tmp):
    engine = _engine(workspace_tmp)
    engine.add_text("x", item_height=30.0)
    engine.clear()
    assert engine.visible_count() == 0
    assert engine.is_duplicate("x") is False


def test_scrolling_mode_uses_danmu_engine_not_fp_engine(workspace_tmp):
    """配置 scrolling 时不应误用 FloatingPanelEngine（由 main 路由保证；此处测 resolve）。"""
    from app.config_defaults import resolve_danmu_render_mode

    store = ConfigStore(db_path=workspace_tmp / "mode.db")
    store.set("danmu_render_mode", "scrolling")
    assert resolve_danmu_render_mode(store) == "scrolling"
