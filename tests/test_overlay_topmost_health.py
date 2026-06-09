"""运行期 HWND_TOPMOST 健康检查与独占全屏风险提示。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from app.application.web_runtime_state import WebRuntimeState
from app.config_store import ConfigStore
from app.danmu_engine import DanmuEngine
from app.floating_panel_engine import FloatingPanelEngine
from app.floating_panel_overlay import FloatingPanelOverlay
from app.overlay import DanmuOverlay
from app.win32_overlay_zorder import probe_exclusive_fullscreen_risk, reassert_hwnd_topmost
from main import DanmuApp
from PyQt6.QtCore import QRect
from app.application.stats_state import StatsState
from tests.conftest import FakeTimer, bind_minimal_danmu_app
from tests.fakes import FakeConfig, FakeEngine, FakeLifetimeStats, FakeSessionRunLog


def _bind_display_facade(app) -> None:
    for name in (
        "_danmu_render_mode",
        "_overlay_display_enabled",
        "_floating_panel_v2_enabled",
        "_active_overlay_layer",
        "_overlay_own_hwnds",
        "_reassert_pet_above_overlays",
        "_reassert_active_overlay_topmost",
        "_update_overlay_compat_warning",
        "_on_topmost_health_tick",
        "_ensure_web_runtime_state",
        "_on_app_focus_changed",
    ):
        method = getattr(DanmuApp, name)
        object.__setattr__(app, name, method.__get__(app, DanmuApp))


@pytest.fixture()
def topmost_app(qapp, workspace_tmp):
    store = ConfigStore(db_path=workspace_tmp / "topmost.db")
    engine = DanmuEngine(store)
    overlay = DanmuOverlay(store, engine)
    overlay.setGeometry(0, 0, 800, 600)
    fp_engine = FloatingPanelEngine(store)
    fp_overlay = FloatingPanelOverlay(store, fp_engine)
    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(
        app,
        config=store,
        engine=engine,
        overlay=overlay,
        floating_panel_engine=fp_engine,
        floating_panel_overlay=fp_overlay,
    )
    app._topmost_health_timer = FakeTimer()
    _bind_display_facade(app)
    app._ensure_web_runtime_state = DanmuApp._ensure_web_runtime_state.__get__(app, DanmuApp)
    return app, engine, overlay, fp_overlay


def test_topmost_timer_lifecycle_on_start_stop(topmost_app):
    app, engine, overlay, _ = topmost_app
    engine.running = True
    overlay.show()
    app._sync_overlay_visibility = Mock()
    app._sync_floating_panel_visibility = Mock()
    app._reassert_active_overlay_topmost = Mock()
    app._sync_pet_window_visibility = Mock()
    app._pool_topup_timer = FakeTimer()
    app._start_meme_barrage_timers = Mock()
    app.tray = Mock()
    app.state_changed = Mock()
    app._set_error_status_safe = Mock()
    app.logger = Mock()
    app._sync_mic_service = Mock()
    app._danmu_read_service = None

    # Exercise only the timer lines from start() after overlay sync.
    app._topmost_health_timer.start()
    app._reassert_active_overlay_topmost()
    assert app._topmost_health_timer.active

    app._topmost_health_timer.stop()
    app._ensure_web_runtime_state().set_overlay_compat_warning("")
    assert not app._topmost_health_timer.active


def test_show_event_applies_win32_click_through(topmost_app, qapp):
    app, _engine, overlay, _ = topmost_app
    calls: list[bool] = []
    overlay._apply_win32_click_through = lambda: calls.append(True)
    overlay.hide()
    qapp.processEvents()
    overlay.show()
    qapp.processEvents()
    assert calls


def test_health_tick_reasserts_scrolling_overlay(topmost_app, qapp):
    app, engine, overlay, _ = topmost_app
    engine.running = True
    overlay.show()
    qapp.processEvents()
    calls: list[str] = []
    overlay.reassert_topmost_zorder = lambda: calls.append("overlay")
    app._reassert_pet_above_overlays = Mock()
    app._update_overlay_compat_warning = Mock()
    app._on_topmost_health_tick()
    assert calls == ["overlay"]


def test_health_tick_reasserts_floating_panel(topmost_app, qapp, monkeypatch):
    app, engine, _, fp_overlay = topmost_app
    app.config.set("danmu_render_mode", "floating_panel")
    engine.running = True
    fp_overlay.show()
    qapp.processEvents()
    calls: list[str] = []
    fp_overlay.reassert_topmost_zorder = lambda: calls.append("fp")
    app._reassert_pet_above_overlays = Mock()
    app._update_overlay_compat_warning = Mock()
    app._on_topmost_health_tick()
    assert calls == ["fp"]


def test_health_tick_skips_when_hidden(topmost_app):
    app, engine, overlay, _ = topmost_app
    engine.running = True
    assert not overlay.isVisible()
    calls: list[str] = []
    overlay.reassert_topmost_zorder = lambda: calls.append("overlay")
    app._on_topmost_health_tick()
    assert calls == []
    assert app.web_runtime_state.overlay_compat_warning == ""


def test_focus_changed_delegates_to_active_overlay(topmost_app, qapp):
    app, engine, overlay, _ = topmost_app
    engine.running = True
    overlay.show()
    qapp.processEvents()
    calls: list[str] = []
    app._reassert_active_overlay_topmost = lambda: calls.append("reassert")
    app._on_app_focus_changed(None, None)
    assert calls == ["reassert"]


def test_probe_exclusive_fullscreen_risk(monkeypatch):
    import app.win32_overlay_zorder as mod

    if mod.sys.platform != "win32":
        pytest.skip("win32 only")

    monkeypatch.setattr(mod, "_read_window_rect", lambda hwnd: (0, 0, 1920, 1080))
    monkeypatch.setattr(mod, "_GetForegroundWindow", lambda: 100)
    assert probe_exclusive_fullscreen_risk(
        overlay_hwnd=100,
        screen_x=0,
        screen_y=0,
        screen_w=1920,
        screen_h=1080,
        own_hwnds=(100,),
    ) is False
    monkeypatch.setattr(mod, "_GetForegroundWindow", lambda: 9999)
    monkeypatch.setattr(mod, "_GetWindowLong", lambda hwnd, idx: 0)
    assert probe_exclusive_fullscreen_risk(
        overlay_hwnd=100,
        screen_x=0,
        screen_y=0,
        screen_w=1920,
        screen_h=1080,
        own_hwnds=(),
    ) is True
    monkeypatch.setattr(mod, "_GetWindowLong", lambda hwnd, idx: mod._WS_CAPTION)
    assert probe_exclusive_fullscreen_risk(
        overlay_hwnd=100,
        screen_x=0,
        screen_y=0,
        screen_w=1920,
        screen_h=1080,
        own_hwnds=(),
    ) is False


def test_apply_overlay_exstyles_sets_layered_and_transparent_bits(monkeypatch):
    import sys

    import app.win32_overlay_zorder as mod

    if mod.sys.platform != "win32":
        pytest.skip("win32 only")

    stored: dict[int, int] = {mod._GWL_EXSTYLE: 0}

    monkeypatch.setattr(mod, "_GetWindowLong", lambda hwnd, idx: stored.get(idx, 0))
    monkeypatch.setattr(
        mod,
        "_SetWindowLong",
        lambda hwnd, idx, value: stored.__setitem__(idx, value),
    )

    mod.apply_overlay_exstyles(12345, click_through=True)
    assert stored[mod._GWL_EXSTYLE] & mod._WS_EX_LAYERED
    assert stored[mod._GWL_EXSTYLE] & mod._WS_EX_TRANSPARENT

    mod.apply_overlay_exstyles(12345, click_through=False)
    assert stored[mod._GWL_EXSTYLE] & mod._WS_EX_LAYERED
    assert not (stored[mod._GWL_EXSTYLE] & mod._WS_EX_TRANSPARENT)


def test_reassert_hwnd_topmost_noop_on_zero(monkeypatch):
    import app.win32_overlay_zorder as mod

    called: list[int] = []
    if mod.sys.platform == "win32":
        monkeypatch.setattr(mod, "_SetWindowPos", lambda *a, **k: called.append(1))
    reassert_hwnd_topmost(0)
    assert called == []


def test_status_includes_overlay_compat_warning(monkeypatch):
    engine = FakeEngine()
    engine.running = True
    app = SimpleNamespace(
        config=FakeConfig({}),
        engine=engine,
        reply_buffer=SimpleNamespace(size=lambda: 0),
        stats_state=StatsState(),
        web_runtime_state=WebRuntimeState(),
        lifetime_stats=FakeLifetimeStats(),
        session_run_log=FakeSessionRunLog(),
        personae=SimpleNamespace(get_active=lambda: []),
        visible_display_count=lambda: 0,
        build_live_status_snapshot=lambda: None,
        _region_selection_state="idle",
    )
    app.web_runtime_state.set_overlay_compat_warning("fullscreen-risk")
    monkeypatch.setattr(
        "app.model_selection.resolve_model_status",
        lambda config: {},
    )
    monkeypatch.setattr(
        "app.web_api.capture_region.capture_region_mode",
        lambda config: "full_screen",
    )
    status = DanmuApp.build_status_snapshot(app)
    assert status["overlay_compat_warning"] == "fullscreen-risk"


def test_status_clears_overlay_compat_warning_when_stopped(monkeypatch):
    engine = FakeEngine()
    engine.running = False
    app = SimpleNamespace(
        config=FakeConfig({}),
        engine=engine,
        reply_buffer=SimpleNamespace(size=lambda: 0),
        stats_state=StatsState(),
        web_runtime_state=WebRuntimeState(),
        lifetime_stats=FakeLifetimeStats(),
        session_run_log=FakeSessionRunLog(),
        personae=SimpleNamespace(get_active=lambda: []),
        visible_display_count=lambda: 0,
        build_live_status_snapshot=lambda: None,
        _region_selection_state="idle",
    )
    app.web_runtime_state.set_overlay_compat_warning("should-not-leak")
    monkeypatch.setattr(
        "app.model_selection.resolve_model_status",
        lambda config: {},
    )
    monkeypatch.setattr(
        "app.web_api.capture_region.capture_region_mode",
        lambda config: "full_screen",
    )
    status = DanmuApp.build_status_snapshot(app)
    assert status["overlay_compat_warning"] == ""
