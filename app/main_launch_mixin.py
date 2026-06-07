"""DanmuApp 启动与控制台 attach Mixin（W-REFACTOR-MAIN-001）。

职责边界：
- Web 控制台打开/导航（_open_web_console、_open_web_console_when_ready）
- pywebview attach 重试与调度（_retry_webview_attach、_schedule_webview_attach）

与 DanmuApp 关系：通过 self 访问 webview_shell、web_server、web_launch_mode 等字段。
DanmuApp 通过多继承获得这些方法。

代码归属判断：Web 控制台/pywebview 的启动、attach、导航逻辑放这里。
"""

from __future__ import annotations


class DanmuAppLaunchMixin:
    """启动 Mixin：DanmuApp 通过多继承获得这些方法。

    通过 self 访问 DanmuApp 的 webview_shell、web_server、web_launch_mode 等字段。
    """

    def _open_web_console_when_ready(
        self,
        path: str = "/",
        *,
        use_browser: bool = False,
        attempt: int = 0,
        on_webview_handshake_failed=None,
    ) -> None:
        from app.webview_shell import open_web_console_when_ready

        open_web_console_when_ready(
            self,
            path,
            use_browser=use_browser,
            attempt=attempt,
            on_webview_handshake_failed=on_webview_handshake_failed,
        )

    def _retry_webview_attach(self, path: str, schedule_attempt: int) -> None:
        from app.webview_shell import retry_webview_attach

        retry_webview_attach(self, path, schedule_attempt)

    def _schedule_webview_attach(self, initial_path: str, *, attempt: int = 0) -> None:
        from app.webview_shell import schedule_webview_attach

        schedule_webview_attach(self, initial_path, attempt=attempt)

    def _open_web_console(self, path: str = "/") -> None:
        shell = getattr(self, "webview_shell", None)
        if shell and shell.is_running():
            shell.open(path)
            return
        if shell and shell.is_handshake_pending():
            shell.request_navigate(path)
            return
        if (
            shell
            and shell.handshake_failed
            and self.web_launch_mode == "webview"
            and self.web_server
        ):
            return
        if self.web_launch_mode == "webview" and self.web_server:
            self._open_web_console_when_ready(path, use_browser=False)
            return
        if self.web_launch_mode == "browser" and self.web_server:
            self._open_web_console_when_ready(path, use_browser=True)

    def show_settings(self) -> None:
        if self.web_server:
            self._open_web_console("/#settings")
