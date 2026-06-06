"""FloatingPanel render lifecycle: 事件驱动 + 静止停表 + 配置应用。

W-FP-002 单测：覆盖
- 初始 timer 非 active；
- feed() 启动 timer；
- 队列空时 timer 自动停表；
- 上限裁剪；
- apply_config 行为；
- set_display_mode 显隐控制。
"""
from __future__ import annotations

import pytest
from app.config_store import ConfigStore
from app.floating_panel import FloatingPanel
from PyQt6.QtWidgets import QApplication


@pytest.fixture()
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def fp_setup(qapp, workspace_tmp):
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("floating_panel_max_items", "60")
    store.set("floating_panel_font_size", "18")
    store.set("floating_panel_opacity", "85")
    store.set("floating_panel_speed", "1.5")
    store.set("floating_panel_click_through", "1")
    panel = FloatingPanel(store)
    panel.set_display_mode("floating_panel")
    panel.resize(400, 600)
    qapp.processEvents()
    return store, panel


def test_initial_timer_not_active(fp_setup):
    """新建后队列空，timer 永不启动。"""
    _, panel = fp_setup
    assert panel.active_count() == 0
    assert not panel.is_render_active()


def test_feed_starts_timer(fp_setup, qapp):
    """feed() 触发 _kick_render，timer 进入 active。"""
    _, panel = fp_setup
    panel.feed("hello floating")
    assert panel.active_count() == 1
    assert panel.is_render_active()
    qapp.processEvents()


def test_active_items_drain_after_enough_ticks(fp_setup, qapp):
    """足够多帧后最早条目滚出顶部，自动停表。"""
    _, panel = fp_setup
    # 把速度调到最大以加速测试
    panel._speed = 5.0
    for i in range(5):
        panel.feed(f"item-{i}")
    qapp.processEvents()
    assert panel.is_render_active()

    # 模拟 ~2 秒动画（120 帧 @ 60fps）
    for _ in range(200):
        panel._tick()
        if not panel._active_items:
            break

    assert panel.active_count() == 0
    assert not panel.is_render_active()


def test_max_items_caps_queue(fp_setup, qapp):
    """超过 floating_panel_max_items 时按 FIFO 丢最旧。"""
    store, panel = fp_setup
    store.set("floating_panel_max_items", "10")
    panel.apply_config()

    for i in range(15):
        panel.feed(f"line-{i}")
    qapp.processEvents()
    assert panel.active_count() == 10
    contents = [it.content for it in panel._active_items]
    # FIFO 丢最旧 → 留存 line-5..line-14
    assert contents[0] == "line-5"
    assert contents[-1] == "line-14"


def test_apply_config_shrinks_max_items(fp_setup, qapp):
    """运行时调小 max_items 立即按 FIFO 裁剪。"""
    store, panel = fp_setup
    for i in range(20):
        panel.feed(f"row-{i}")
    qapp.processEvents()
    assert panel.active_count() == 20

    store.set("floating_panel_max_items", "5")
    panel.apply_config()
    assert panel.active_count() == 5


def test_set_display_mode_applies_default_geometry_without_resize(qapp, workspace_tmp):
    """首次 floating_panel 模式须落到 400×600 默认区，勿误用 Qt 预显示 640×480 或 show 后 16×16。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    panel = FloatingPanel(store)
    panel.set_display_mode("floating_panel")
    qapp.processEvents()
    assert panel.isVisible()
    assert panel.width() >= 400
    assert panel.height() >= 600
    assert panel._geometry_initialized is True


def test_set_display_mode_overlay_hides_panel(fp_setup):
    """set_display_mode('overlay') 隐藏悬浮窗。"""
    _, panel = fp_setup
    assert panel.isVisible()

    panel.set_display_mode("overlay")
    assert not panel.isVisible()


def test_set_display_mode_both_keeps_visible(fp_setup):
    """set_display_mode('both') 保持显示。"""
    _, panel = fp_setup
    assert panel.isVisible()
    panel.set_display_mode("both")
    assert panel.isVisible()


def test_set_display_mode_unknown_falls_back_to_overlay(fp_setup):
    """非法 display_mode 回落为 overlay（与 _clamp_choice 一致）。"""
    _, panel = fp_setup
    assert panel.isVisible()
    panel.set_display_mode("weird")
    assert not panel.isVisible()
    assert panel._display_mode == "overlay"


def test_dedup_window_skips_recent_text(fp_setup, qapp):
    """deque(30) 去重窗口：近期相同文本不再入队。"""
    _, panel = fp_setup
    panel.feed("repeat me")
    panel.feed("repeat me")
    qapp.processEvents()
    assert panel.active_count() == 1


def test_feed_empty_text_ignored(fp_setup, qapp):
    """空文本不进入队列。"""
    _, panel = fp_setup
    panel.feed("")
    qapp.processEvents()
    assert panel.active_count() == 0
    assert not panel.is_render_active()


def test_overlay_mode_does_not_accept_feed(fp_setup, qapp):
    """display_mode='overlay' 时 feed() 直接 return，不入队。"""
    store, panel = fp_setup
    panel.set_display_mode("overlay")
    panel.feed("ignored")
    qapp.processEvents()
    assert panel.active_count() == 0
    assert not panel.is_render_active()


def test_apply_config_respects_config_defaults(qapp, workspace_tmp):
    """apply_config 从 ConfigStore 读取最新值。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("floating_panel_font_size", "24")
    store.set("floating_panel_opacity", "50")
    store.set("floating_panel_speed", "2.5")
    store.set("floating_panel_click_through", "0")
    panel = FloatingPanel(store)
    # __init__ 已读一次；改完后再 apply
    panel.apply_config()
    assert panel._font_size == 24
    assert panel._opacity_pct == 50
    assert abs(panel._speed - 2.5) < 1e-6
    assert panel._click_through is False


def test_apply_config_clamps_invalid_values(qapp, workspace_tmp):
    """apply_config 对非法值做钳位保护。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("floating_panel_font_size", "999")
    store.set("floating_panel_opacity", "200")
    store.set("floating_panel_max_items", "0")
    store.set("floating_panel_speed", "100")
    panel = FloatingPanel(store)
    panel.apply_config()
    assert panel._font_size == 48
    assert panel._opacity_pct == 100
    assert panel._max_items == 5
    assert panel._speed == 5.0


# ---------- W-FP-003：DanmuApp 旁路分发与配置切换 ----------


def _make_minimal_danmu_app(store, panel):
    """构造一个最小 DanmuApp（绕开 __init__），注入 floating_panel / config。"""
    from main import DanmuApp

    app = DanmuApp.__new__(DanmuApp)
    object.__setattr__(app, "config", store)
    object.__setattr__(app, "floating_panel", panel)
    object.__setattr__(app, "logger", type("L", (), {
        "debug": lambda *a, **k: None,
        "info": lambda *a, **k: None,
        "warning": lambda *a, **k: None,
        "error": lambda *a, **k: None,
    })())
    return app


def test_floating_panel_enabled_respects_display_mode(qapp, workspace_tmp):
    """_floating_panel_enabled 依据 display_mode 决定。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    panel = FloatingPanel(store)
    app = _make_minimal_danmu_app(store, panel)

    store.set("display_mode", "overlay")
    assert app._floating_panel_enabled() is False

    store.set("display_mode", "floating_panel")
    assert app._floating_panel_enabled() is True

    store.set("display_mode", "both")
    assert app._floating_panel_enabled() is True

    store.set("display_mode", "")
    assert app._floating_panel_enabled() is False  # 默认 overlay


def test_feed_floating_panel_routes_to_panel_when_enabled(qapp, workspace_tmp):
    """display_mode=floating_panel 时 _feed_floating_panel 调用 panel.feed。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("display_mode", "floating_panel")
    panel = FloatingPanel(store)
    panel.set_display_mode("floating_panel")
    panel.resize(400, 600)
    qapp.processEvents()
    app = _make_minimal_danmu_app(store, panel)

    app._feed_floating_panel("hello 旁路", "测试")
    qapp.processEvents()
    assert panel.active_count() == 1
    assert panel._active_items[0].content == "hello 旁路"


def test_feed_floating_panel_skips_when_overlay_mode(qapp, workspace_tmp):
    """display_mode=overlay 时 _feed_floating_panel 直接 return。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("display_mode", "overlay")
    panel = FloatingPanel(store)
    app = _make_minimal_danmu_app(store, panel)

    app._feed_floating_panel("ignored", "")
    qapp.processEvents()
    assert panel.active_count() == 0


def test_feed_floating_panel_swallows_exceptions(qapp, workspace_tmp):
    """panel.feed 抛异常时主链路不受影响（不传播）。"""
    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("display_mode", "floating_panel")
    panel = FloatingPanel(store)
    panel.set_display_mode("floating_panel")
    panel.resize(400, 600)
    qapp.processEvents()
    app = _make_minimal_danmu_app(store, panel)

    def boom(*a, **k):
        raise RuntimeError("panel broken")
    panel.feed = boom  # type: ignore[assignment]

    # 不应抛
    app._feed_floating_panel("safe", "")


def test_consume_reply_queue_ends_with_floating_panel_feed(qapp, workspace_tmp):
    """_consume_reply_queue 末尾调用 _feed_floating_panel（通过 monkeypatch 验证）。"""
    from main import DanmuApp
    from tests.conftest import bind_minimal_danmu_app
    from tests.fakes import (
        FakeEngine,
        FakeHistoryWriter,
        FakeLifetimeStats,
        FakeLogger,
        FakeTimer,
    )
    from app.reply_queue import AIReplyFIFOBuffer

    store = ConfigStore(db_path=workspace_tmp / "config.db")
    store.set("display_mode", "floating_panel")
    panel = FloatingPanel(store)
    panel.set_display_mode("floating_panel")
    panel.resize(400, 600)
    qapp.processEvents()

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(
        app,
        config=store,
        floating_panel=panel,
        engine=FakeEngine(),
        history_writer=FakeHistoryWriter(),
        reply_buffer=AIReplyFIFOBuffer(max_items=8),
        reply_timer=FakeTimer(),
        logger=FakeLogger(),
        lifetime_stats=FakeLifetimeStats(),
    )
    # 关键：把 bound method 重新绑定到 app（bind_minimal_danmu_app 不绑定私有方法）
    app._consume_reply_queue = DanmuApp._consume_reply_queue.__get__(app, DanmuApp)
    app._feed_floating_panel = DanmuApp._feed_floating_panel.__get__(app, DanmuApp)
    app._floating_panel_enabled = DanmuApp._floating_panel_enabled.__get__(app, DanmuApp)
    app._update_stats = lambda *, success: None
    app._record_scene_memory_display = lambda *a, **k: None
    app._broadcast_live_overlay_item = lambda *a, **k: None
    app._current_batch = None
    from app.personae import persona_display_name  # noqa: F401
    app.personae = type("P", (), {
        "display_name": staticmethod(lambda _id: _id)
    })()

    called = []
    original = app._feed_floating_panel

    def spy(content, persona):
        called.append((content, persona))
        return original(content, persona)
    app._feed_floating_panel = spy  # type: ignore[assignment]

    from app.reply_queue import QueuedReply
    import time

    qr = QueuedReply(
        content="旁路测试",
        persona_id="default",
        batch_id=1,
        batch_index=0,
        content_index=0,
        screenshot_id=1,
        screenshot_round=1,
        scene_generation=0,
        captured_at=time.time(),
        source="ai",
        is_fallback=False,
    )
    app.reply_buffer.extend([qr])
    app._consume_reply_queue()
    qapp.processEvents()
    assert any(c[0] == "旁路测试" for c in called), f"_feed_floating_panel not called: {called}"
    assert panel.active_count() == 1

