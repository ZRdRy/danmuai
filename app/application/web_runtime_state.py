"""Web 控制台错误条与 Overlay 布局缓存；经 build_status_snapshot 对外展示。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebRuntimeState:
    """Web/API 不得直接读取本对象；须走 DanmuApp.build_status_snapshot()。"""

    error_message: str = ""
    is_error: bool = False
    cached_danmu_lines: int = 0
    cached_layout_mode: str = "fullscreen"

    def set_error_status(self, message: str, *, is_error: bool) -> None:
        self.error_message = str(message or "")
        self.is_error = bool(is_error)

    def set_overlay_cache(self, *, danmu_lines: int, layout_mode: str) -> None:
        self.cached_danmu_lines = int(danmu_lines or 0)
        self.cached_layout_mode = str(layout_mode or "fullscreen")
