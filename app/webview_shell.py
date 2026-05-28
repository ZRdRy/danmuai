"""pywebview desktop shell for the local DanmuAI web console."""

from __future__ import annotations

import json
import multiprocessing
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

from app.bundle_paths import append_frozen_log, frozen_log_path, is_frozen

if TYPE_CHECKING:
    from app.web_console import WebConsoleServer

_START_TIMEOUT_SEC = 20.0
_SERVER_POLL_SEC = 12.0
_FROZEN_SERVER_POLL_SEC = 30.0
_NAV_POLL_SEC = 0.25
_BROWSER_PROBE_SEC = 3.0


def preferred_webview_gui() -> str | None:
    if sys.platform == "win32":
        return "edgechromium"
    if sys.platform == "darwin":
        return "cocoa"
    return "gtk"


def wait_for_http_server(base_url: str, timeout: float = _SERVER_POLL_SEC) -> bool:
    deadline = time.monotonic() + timeout
    probe = f"{base_url.rstrip('/')}/api/session"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(probe, timeout=0.6) as resp:
                if resp.status != 200:
                    continue
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                if data.get("token"):
                    return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            time.sleep(0.15)
    return False


def notify_web_console_failure(danmu_app, reason_key: str, *, detail: str = "") -> None:
    """主线程弹窗 + 托盘气泡；HTTP 线程请经 QTimer.singleShot 调用本函数。"""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QMessageBox, QSystemTrayIcon

    from app.translations import tr

    server = getattr(danmu_app, "web_server", None)
    base_url = server.base_url if server else "http://127.0.0.1:18765"
    log_path = frozen_log_path()
    message = tr(reason_key).format(
        log_path=log_path,
        base_url=base_url,
        detail=detail,
    )

    def _show() -> None:
        tray = getattr(getattr(danmu_app, "tray", None), "tray", None)
        if tray is not None and QSystemTrayIcon.isSystemTrayAvailable():
            tray.showMessage(
                "DanmuAI",
                message[:240],
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )
        QMessageBox.warning(None, tr("app.error_title"), message)

    QTimer.singleShot(0, _show)


def _ensure_server_ready(server: WebConsoleServer) -> bool:
    poll = _FROZEN_SERVER_POLL_SEC if is_frozen() else _SERVER_POLL_SEC
    if server.wait_ready(timeout=poll):
        return True
    if wait_for_http_server(server.base_url, timeout=poll):
        return True
    danmu_app = server.bridge.danmu_app
    danmu_app.logger.error(
        f"Web 控制台未就绪: {server.base_url}（请查 startup.log 或端口占用）"
    )
    append_frozen_log(f"web console not ready: {server.base_url}")
    notify_web_console_failure(
        danmu_app,
        "web_console.not_ready",
        detail=server.base_url,
    )
    if wait_for_http_server(server.base_url, timeout=_BROWSER_PROBE_SEC):
        _fallback_to_system_browser(server, "/#settings", "web console slow start")
    return False


def _fallback_to_system_browser(server: WebConsoleServer, path: str, reason: str) -> None:
    from app.web_console import open_web_console_browser

    server.bridge.danmu_app.logger.warning(
        f"pywebview 不可用，改用系统浏览器: {reason}"
    )
    append_frozen_log(f"fallback to system browser: {reason}")
    open_web_console_browser(server, path)


def _nav_poll_loop(window: Any, nav_queue: Any, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            url = nav_queue.get(timeout=_NAV_POLL_SEC)
        except Exception:
            continue
        if url is None:
            break
        try:
            window.load_url(url)
            window.show()
            window.restore()
            append_frozen_log(f"pywebview navigate: {url}")
        except Exception as exc:
            append_frozen_log(f"pywebview navigate failed: {exc!r}")


def _webview_worker(
    url: str,
    title: str,
    gui: str | None,
    ready_queue: Any,
    nav_queue: Any,
) -> None:
    """Runs in child process; this process's main thread owns webview.start()."""
    multiprocessing.freeze_support()
    stop_nav = threading.Event()
    try:
        import webview

        def on_closing(*_args, **_kwargs):
            return True

        def on_loaded(window):
            window.show()
            append_frozen_log("pywebview window loaded")

        window = webview.create_window(
            title,
            url,
            width=1280,
            height=820,
            min_size=(960, 640),
            hidden=True,
            background_color="#FDFBF7",
        )
        window.events.closing += on_closing
        window.events.loaded += on_loaded

        # Must signal before webview.start(); do NOT call window.show() here — on Windows
        # show() before start() can block the child main thread and never reach put(True).
        ready_queue.put(True)
        append_frozen_log("pywebview ready handshake sent")

        threading.Thread(
            target=_nav_poll_loop,
            args=(window, nav_queue, stop_nav),
            name="DanmuWebViewNav",
            daemon=True,
        ).start()

        if gui:
            webview.start(debug=False, gui=gui)
        else:
            webview.start(debug=False)
        stop_nav.set()
        try:
            nav_queue.put(None)
        except Exception:
            pass
    except Exception as exc:
        append_frozen_log(f"pywebview worker failed: {exc!r}")
        try:
            ready_queue.put(str(exc))
        except Exception:
            pass


def _webview_process_main(
    url: str,
    title: str,
    gui: str | None,
    ready_queue: Any,
    nav_queue: Any,
) -> None:
    _webview_worker(url, title, gui, ready_queue, nav_queue)


class WebViewShell:
    """Runs pywebview in a child process so Qt keeps the main GUI loop."""

    def __init__(self, server: WebConsoleServer, title: str = "DanmuAI"):
        self.server = server
        self.title = title
        self._process: multiprocessing.Process | None = None
        self._ready_queue: multiprocessing.Queue | None = None
        self._nav_queue: multiprocessing.Queue | None = None
        self._started = False

    def is_running(self) -> bool:
        return self._started and self._process is not None and self._process.is_alive()

    def _url(self, path: str = "/") -> str:
        base = self.server.base_url.rstrip("/")
        if not path or path == "/":
            return f"{base}/"
        if path.startswith("#"):
            return f"{base}/{path}"
        if path.startswith("/"):
            return f"{base}{path}"
        return f"{base}/{path}"

    def start(self, initial_path: str = "/") -> bool:
        if self.is_running():
            self.open(initial_path)
            return True

        if not _ensure_server_ready(self.server):
            return False

        self._pending_path = initial_path
        url = self._url(initial_path)
        gui = preferred_webview_gui()
        ctx = multiprocessing.get_context("spawn")
        self._ready_queue = ctx.Queue()
        self._nav_queue = ctx.Queue()
        self._process = ctx.Process(
            target=_webview_process_main,
            args=(url, self.title, gui, self._ready_queue, self._nav_queue),
            name="DanmuWebView",
            daemon=True,
        )
        self._process.start()
        try:
            signal = self._ready_queue.get(timeout=_START_TIMEOUT_SEC)
        except Exception:
            signal = "timeout waiting for pywebview window"
        return self._finish_start(signal, initial_path)

    def _finish_start(self, signal, initial_path: str) -> bool:
        if signal is not True:
            error = str(signal)
            self.server.bridge.danmu_app.logger.error(
                f"pywebview 启动失败: {error}"
            )
            append_frozen_log(f"pywebview start failed: {error}")
            self._terminate()
            _fallback_to_system_browser(self.server, initial_path, error)
            return False

        self._started = True
        append_frozen_log(f"pywebview process started url={self._url(initial_path)}")
        return True

    def open(self, path: str = "/") -> None:
        if not self.is_running():
            if not self.start(path):
                return
            return

        url = self._url(path)
        nav_queue = self._nav_queue
        if nav_queue is not None:
            try:
                nav_queue.put(url)
                return
            except Exception as exc:
                _fallback_to_system_browser(self.server, path, str(exc))
                return

        _fallback_to_system_browser(self.server, path, "nav queue unavailable")

    def _terminate(self) -> None:
        proc = self._process
        nav_queue = self._nav_queue
        self._process = None
        self._ready_queue = None
        self._nav_queue = None
        self._started = False
        if nav_queue is not None:
            try:
                nav_queue.put(None)
            except Exception:
                pass
        if proc is None:
            return
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2.0)

    def destroy(self) -> None:
        self._terminate()


def attach_webview_shell(
    danmu_app,
    server: WebConsoleServer,
    *,
    initial_path: str = "/",
) -> WebViewShell:
    shell = WebViewShell(server)
    danmu_app.webview_shell = shell
    shell.start(initial_path)
    return shell
