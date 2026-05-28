"""Tests for pywebview shell helpers."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.webview_shell import (
    WebViewShell,
    _webview_worker,
    notify_web_console_failure,
    preferred_webview_gui,
    wait_for_http_server,
)


def test_preferred_webview_gui_windows():
    with patch.object(sys, "platform", "win32"):
        assert preferred_webview_gui() == "edgechromium"


def test_wait_for_http_server_success():
    class FakeResp:
        status = 200

        def read(self):
            return b'{"token":"abc","base_url":"http://127.0.0.1:18765"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        assert wait_for_http_server("http://127.0.0.1:18765", timeout=1.0) is True


def test_wait_for_http_server_rejects_missing_token():
    class FakeResp:
        status = 200

        def read(self):
            return b'{"base_url":"http://127.0.0.1:18765"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        assert wait_for_http_server("http://127.0.0.1:18765", timeout=0.5) is False


def test_webview_shell_url_hash_path():
    server = MagicMock()
    server.base_url = "http://127.0.0.1:18765"
    shell = WebViewShell(server)
    assert shell._url("/#settings") == "http://127.0.0.1:18765/#settings"
    assert shell._url("#settings") == "http://127.0.0.1:18765/#settings"


def test_webview_shell_open_delegates_to_start_when_not_running(monkeypatch):
    server = MagicMock()
    server.base_url = "http://127.0.0.1:18765"
    server.bridge.danmu_app.logger = MagicMock()
    shell = WebViewShell(server)
    shell._started = False
    shell._process = None

    called = []

    def fake_start(path):
        called.append(path)
        return False

    monkeypatch.setattr(shell, "start", fake_start)

    shell.open("/#settings")
    assert called == ["/#settings"]


def test_webview_shell_open_uses_nav_queue_when_running():
    server = MagicMock()
    server.base_url = "http://127.0.0.1:18765"
    shell = WebViewShell(server)
    shell._started = True
    shell._process = MagicMock()
    shell._process.is_alive.return_value = True
    shell._nav_queue = MagicMock()

    shell.open("/#settings")

    shell._nav_queue.put.assert_called_once_with("http://127.0.0.1:18765/#settings")


def test_webview_worker_puts_true_before_start(monkeypatch):
    ready_puts = []

    class FakeReadyQueue:
        def put(self, value):
            ready_puts.append(value)

    class FakeEventSlot:
        def __iadd__(self, _handler):
            return self

    class FakeWindow:
        events = type("E", (), {"loaded": FakeEventSlot(), "closing": FakeEventSlot()})()

    fake_webview = MagicMock()
    fake_webview.create_window.return_value = FakeWindow()
    start_called = []

    def fake_start(**_kwargs):
        start_called.append(True)
        assert ready_puts == [True]

    fake_webview.start.side_effect = fake_start
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr("app.webview_shell.append_frozen_log", lambda _msg: None)

    nav_queue = MagicMock()
    _webview_worker("http://127.0.0.1:18765/", "DanmuAI", "edgechromium", FakeReadyQueue(), nav_queue)

    assert ready_puts == [True]
    assert start_called


def test_webview_worker_start_error_puts_error(monkeypatch):
    ready_puts = []

    class FakeReadyQueue:
        def put(self, value):
            ready_puts.append(value)

    class FakeEventSlot:
        def __iadd__(self, _handler):
            return self

    class FakeWindow:
        events = type("E", (), {"loaded": FakeEventSlot(), "closing": FakeEventSlot()})()

    fake_webview = MagicMock()
    fake_webview.create_window.return_value = FakeWindow()
    fake_webview.start.side_effect = RuntimeError("webview boom")
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr("app.webview_shell.append_frozen_log", lambda _msg: None)

    _webview_worker("http://127.0.0.1:18765/", "DanmuAI", None, FakeReadyQueue(), MagicMock())

    assert ready_puts == [True, "webview boom"]


def test_notify_web_console_failure_schedules_ui(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    danmu = MagicMock()
    danmu.web_server = MagicMock(base_url="http://127.0.0.1:18765")
    danmu.tray = MagicMock()
    danmu.tray.tray = MagicMock()

    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    notify_web_console_failure(danmu, "web_console.startup_failed")
    app.processEvents()

    assert warnings


def test_ensure_server_ready_false_notifies_and_optional_browser(monkeypatch):
    from app import webview_shell

    server = MagicMock()
    server.base_url = "http://127.0.0.1:18765"
    server.wait_ready.return_value = False
    server.bridge.danmu_app.logger = MagicMock()

    notified = []
    fallbacks = []
    monkeypatch.setattr(
        webview_shell,
        "notify_web_console_failure",
        lambda app, key, **kw: notified.append((key, kw)),
    )
    monkeypatch.setattr(webview_shell, "wait_for_http_server", lambda url, timeout: timeout == 3.0)
    monkeypatch.setattr(
        webview_shell,
        "_fallback_to_system_browser",
        lambda s, p, r: fallbacks.append((p, r)),
    )

    assert webview_shell._ensure_server_ready(server) is False
    assert notified
    assert fallbacks == [("/#settings", "web console slow start")]
