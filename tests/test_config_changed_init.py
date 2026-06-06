"""BUG-031: config_changed handler errors must not yield save ok=True."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.web_console_support import SAVE_DONE_EVENT_KEY, SAVE_RESULT_KEY, handle_save_config_request
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_config_changed_connect_after_attach_web_console_in_main_py():
    text = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    attach_idx = text.index("attach_web_console(self)")
    connect_idx = text.index("self.config_changed.connect(self._on_config_changed)")
    assert attach_idx < connect_idx


class _StubDanmuApp(QObject):
    config_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.logger = MagicMock()
        self.set_web_error_status = MagicMock()
        self.config_changed.connect(
            self._on_config_changed,
            Qt.ConnectionType.DirectConnection,
        )

    def _on_config_changed(self) -> None:
        raise RuntimeError("config handler failed")

    def apply_web_config_payload(self, _payload: dict) -> None:
        # Same-thread emit as ConfigService; invoke slot directly for deterministic test delivery.
        self._on_config_changed()


def test_on_config_changed_error_does_not_mark_save_ok(qapp):
    app = _StubDanmuApp()
    bridge = MagicMock()
    bridge.danmu_app = app
    bridge.publish_status = MagicMock()

    done = threading.Event()
    result: dict = {"ok": True}
    payload = {
        "font_size": "24",
        SAVE_DONE_EVENT_KEY: done,
        SAVE_RESULT_KEY: result,
    }

    handle_save_config_request(bridge, payload)

    assert done.is_set()
    assert result["ok"] is False
    assert result.get("error") == "save_failed"
    assert result.get("detail")
