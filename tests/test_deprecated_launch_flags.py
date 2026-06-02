"""废弃 Qt 主窗启动参数须硬错误退出。"""

import os
import sys
from unittest.mock import patch

import pytest
from main import _check_deprecated_launch_args


def test_qt_ui_argv_exits():
    with patch.object(sys, "argv", ["main.py", "--qt-ui"]):
        with pytest.raises(SystemExit) as exc:
            _check_deprecated_launch_args()
        assert exc.value.code == 2


def test_legacy_ui_argv_exits():
    with patch.object(sys, "argv", ["main.py", "--legacy-ui"]):
        with pytest.raises(SystemExit) as exc:
            _check_deprecated_launch_args()
        assert exc.value.code == 2


def test_danmu_qt_ui_env_exits():
    with patch.object(sys, "argv", ["main.py"]):
        with patch.dict(os.environ, {"DANMU_QT_UI": "1"}, clear=False):
            with pytest.raises(SystemExit) as exc:
                _check_deprecated_launch_args()
            assert exc.value.code == 2


def test_danmu_web_console_off_env_exits():
    with patch.object(sys, "argv", ["main.py"]):
        with patch.dict(os.environ, {"DANMU_WEB_CONSOLE": "0"}, clear=False):
            with pytest.raises(SystemExit) as exc:
                _check_deprecated_launch_args()
            assert exc.value.code == 2


def test_default_argv_passes():
    with patch.object(sys, "argv", ["main.py"]):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DANMU_QT_UI", None)
            os.environ.pop("DANMU_WEB_CONSOLE", None)
            _check_deprecated_launch_args()


def test_web_launch_mode_from_argv_browser():
    from app.main_launch import web_launch_mode_from_argv

    with patch.object(sys, "argv", ["main.py", "--web-browser"]):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DANMU_WEB_LAUNCH", None)
            assert web_launch_mode_from_argv() == "browser"


def test_web_launch_mode_from_env():
    from app.main_launch import web_launch_mode_from_argv

    with patch.object(sys, "argv", ["main.py"]):
        with patch.dict(os.environ, {"DANMU_WEB_LAUNCH": "browser"}, clear=False):
            assert web_launch_mode_from_argv() == "browser"
