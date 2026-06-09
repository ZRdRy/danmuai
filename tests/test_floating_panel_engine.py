"""W-FP-V3-002/003：FloatingPanelEngine 连续上滚与竖向间距测试。"""
from __future__ import annotations

from app.config_store import ConfigStore
from app.floating_panel_engine import FloatingPanelEngine


def _engine(tmp_path, **overrides) -> FloatingPanelEngine:
    store = ConfigStore(db_path=tmp_path / "fp_engine.db")
    store.set("dedup_threshold", "1.0")
    for key, value in overrides.items():
        store.set(key, str(value))
    engine = FloatingPanelEngine(store)
    engine.set_panel_height(400.0)
    return engine


def _wait_until_can_accept(engine: FloatingPanelEngine, height: float, *, max_steps: int = 200) -> None:
    steps = 0
    while not engine.can_accept_new_item(height) and steps < max_steps:
        engine.update(0.05, now=float(steps))
        steps += 1
    assert engine.can_accept_new_item(height)


def _pairwise_vertical_gaps(engine: FloatingPanelEngine) -> list[float]:
    items = sorted(engine.visible_items(), key=lambda it: it.current_y)
    gaps: list[float] = []
    for idx in range(len(items) - 1):
        upper, lower = items[idx], items[idx + 1]
        gaps.append(lower.current_y - (upper.current_y + upper.height))
    return gaps


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


def test_can_accept_empty_panel(workspace_tmp):
    engine = _engine(workspace_tmp)
    assert engine.can_accept_new_item(40.0) is True


def test_second_item_blocked_until_trailing_scrolls_up(workspace_tmp):
    engine = _engine(workspace_tmp)
    height = 40.0
    first = engine.add_text("one", item_height=height, now=0.0)
    assert first is not None
    assert engine.can_accept_new_item(height) is False
    assert engine.add_text("two", item_height=height, now=0.1) is None

    _wait_until_can_accept(engine, height)
    second = engine.add_text("two", item_height=height, now=1.0)
    assert second is not None
    assert second.current_y == 400.0
    gap = second.current_y - (first.current_y + first.height)
    assert gap >= engine.min_vertical_gap(height) - 0.01


def test_estimate_entry_delay_positive_when_blocked(workspace_tmp):
    engine = _engine(workspace_tmp)
    height = 40.0
    assert engine.estimate_entry_delay_ms(height) == 100
    engine.add_text("one", item_height=height, now=0.0)
    blocked = engine.estimate_entry_delay_ms(height)
    assert blocked > 50
    assert blocked <= 1000


def test_consecutive_items_vertical_gap_invariant(workspace_tmp):
    engine = _engine(workspace_tmp)
    height = 40.0
    min_gap = engine.min_vertical_gap(height)
    for idx in range(5):
        _wait_until_can_accept(engine, height)
        item = engine.add_text(f"line-{idx}", item_height=height, now=float(idx), skip_dedup=True)
        assert item is not None
        engine.update(0.08, now=float(idx) + 0.5)
        for gap in _pairwise_vertical_gaps(engine):
            assert gap >= min_gap - 0.01


def test_duplicate_rejected(workspace_tmp):
    engine = _engine(workspace_tmp)
    assert engine.add_text("dup", item_height=32.0) is not None
    assert engine.add_text("dup", item_height=32.0) is None


def test_similar_duplicate_rejected(workspace_tmp):
    store = ConfigStore(db_path=workspace_tmp / "fp_lev.db")
    store.set("dedup_threshold", "0.5")
    engine = FloatingPanelEngine(store)
    engine.set_panel_height(400.0)
    assert engine.add_text("哈哈哈哈", item_height=32.0) is not None
    assert engine.add_text("哈哈哈哈啊", item_height=32.0) is None


def test_fade_opacity_near_top(workspace_tmp):
    engine = _engine(workspace_tmp)
    item = engine.add_text("fade", item_height=40.0)
    assert item is not None
    item.current_y = 5.0
    engine.update(0.0)
    assert item.opacity < 1.0


def test_relayout_vertical_gaps_after_height_increase(workspace_tmp):
    engine = _engine(workspace_tmp)
    height = 40.0
    first = engine.add_text("one", item_height=height, skip_dedup=True)
    _wait_until_can_accept(engine, height)
    second = engine.add_text("two", item_height=height, skip_dedup=True)
    assert first is not None and second is not None
    engine.update_item_height(first, 80.0)
    engine.relayout_vertical_gaps()
    gap = second.current_y - (first.current_y + first.height)
    assert gap >= engine.min_vertical_gap(second.height) - 0.01


def test_max_items_trims_only_after_scroll_off(workspace_tmp):
    engine = _engine(workspace_tmp, floating_panel_max_items="3")
    height = 30.0
    for i in range(4):
        _wait_until_can_accept(engine, height)
        engine.add_text(f"line-{i}", item_height=height, now=float(i))
    assert engine.visible_count() == 4
    for _ in range(500):
        engine.update(0.1)
        if engine.visible_count() <= 3:
            break
    assert engine.visible_count() == 3
    assert engine.visible_items()[-1].content == "line-3"


def test_engine_default_speed_is_one(workspace_tmp):
    engine = _engine(workspace_tmp)
    assert engine.pixels_per_second == 120.0


def test_engine_uses_floating_panel_speed_for_pixels_per_second(workspace_tmp):
    engine = _engine(workspace_tmp, floating_panel_speed="3.0")
    assert engine.pixels_per_second == 360.0


def test_items_scroll_upward_until_offscreen_then_removed(workspace_tmp):
    engine = _engine(workspace_tmp)
    item = engine.add_text("scroll-up", item_height=40.0, now=0.0)
    assert item is not None
    engine.update(1.0, now=1.0)
    assert item.current_y == 388.0
    for _ in range(50):
        engine.update(0.1, now=99.0)
        if engine.visible_count() == 0:
            break
    assert engine.visible_count() == 0


def test_engine_does_not_use_hold_or_lifetime_exit_semantics(workspace_tmp):
    engine = _engine(workspace_tmp)
    item = engine.add_text("no-hold", item_height=40.0, now=0.0)
    assert item is not None
    engine.update(0.5, now=10.0)
    assert engine.visible_count() == 1
    assert item.current_y == 388.0


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
