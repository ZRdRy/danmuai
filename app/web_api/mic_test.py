"""麦克风测试 API 领域模块。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DanmuApp


def run_mic_test(app: "DanmuApp", duration_sec: float, send_to_ai: bool) -> dict[str, object]:
    """执行麦克风测试并返回结果。"""
    return app.run_mic_test(duration_sec, send_to_ai=send_to_ai)
