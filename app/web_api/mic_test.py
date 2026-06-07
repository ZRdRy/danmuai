"""麦克风测试 API 领域模块。

路由（由 ``app.web_api.routes`` 注册）：
- ``POST /api/mic/test``：调用 ``app.run_mic_test``（W-AUDIT-FIX-002 之后统一走
  DanmuApp 公共 façade）；HTTP 线程经 ``WebConsoleBridge.invoke_on_main`` 回到主线程
  执行 sounddevice 采集与 TTS 探针。

本模块只做领域逻辑（参数注入 + 调 façade），不直接 import sounddevice 或 numpy。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DanmuApp


def run_mic_test(app: "DanmuApp", duration_sec: float, send_to_ai: bool) -> dict[str, object]:
    """执行麦克风测试并返回结果。"""
    return app.run_mic_test(duration_sec, send_to_ai=send_to_ai)
