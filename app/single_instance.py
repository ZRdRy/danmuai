"""Single-instance guard via QLocalServer (one DanmuAI per user profile)."""

from __future__ import annotations

import hashlib
import os
from typing import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

_ACTIVATE_MSG = b"activate"


def _server_name() -> str:
    appdata = os.environ.get("APPDATA", "").strip() or os.path.expanduser("~")
    digest = hashlib.sha256(appdata.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"DanmuAI-{digest}"


class SingleInstanceGuard:
    def __init__(self) -> None:
        self._name = _server_name()
        self._server: QLocalServer | None = None
        self._activate_handler: Callable[[], None] | None = None

    def try_acquire(self) -> bool:
        """Return True if this process should become the primary instance."""
        probe = QLocalSocket()
        probe.connectToServer(self._name)
        if probe.waitForConnected(500):
            probe.write(_ACTIVATE_MSG)
            probe.flush()
            probe.waitForBytesWritten(1000)
            probe.disconnectFromServer()
            return False

        QLocalServer.removeServer(self._name)
        server = QLocalServer()
        if not server.listen(self._name):
            return True
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def bind_activate(self, handler: Callable[[], None]) -> None:
        self._activate_handler = handler

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        if conn.waitForReadyRead(1000) and conn.readAll().data() == _ACTIVATE_MSG:
            handler = self._activate_handler
            if handler is not None:
                QTimer.singleShot(0, handler)
        conn.disconnectFromServer()
