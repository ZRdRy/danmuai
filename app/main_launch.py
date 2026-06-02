"""Startup argv / env helpers extracted from main.py (W-REFACTOR-MAIN-001)."""

from __future__ import annotations

import os
import sys

DEPRECATED_LAUNCH_MSG = (
    "已移除 Qt 主窗（--qt-ui）。请使用: python main.py 或 python main.py --web-browser\n"
    "设置、日志、人格均在 Web 控制台（http://127.0.0.1:18765）。\n"
)


def check_deprecated_launch_args() -> None:
    reasons: list[str] = []
    if "--qt-ui" in sys.argv or "--legacy-ui" in sys.argv:
        reasons.append("命令行参数 --qt-ui / --legacy-ui")
    env_qt = os.environ.get("DANMU_QT_UI", "").strip().lower()
    if env_qt in ("1", "true", "yes", "on"):
        reasons.append("环境变量 DANMU_QT_UI")
    env_web = os.environ.get("DANMU_WEB_CONSOLE", "").strip().lower()
    if env_web in ("0", "false", "no", "off"):
        reasons.append("环境变量 DANMU_WEB_CONSOLE=0")
    if not reasons:
        return
    sys.stderr.write(DEPRECATED_LAUNCH_MSG)
    sys.stderr.write("废弃入口: " + "、".join(reasons) + "\n")
    sys.exit(2)


def web_launch_mode_from_argv() -> str:
    """webview = pywebview 桌面窗（默认）；browser = 系统浏览器。"""
    if "--web-browser" in sys.argv:
        return "browser"
    env = os.environ.get("DANMU_WEB_LAUNCH", "").strip().lower()
    if env in ("browser", "webview"):
        return env
    return "webview"
