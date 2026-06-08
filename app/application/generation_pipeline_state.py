"""视觉主链路 ID 链的只读投影（screenshot_id / scene_generation 相关元数据）。

Boundary Guard 要求集中经 from_app 读取，禁止在 RuntimeState 内散落 getattr(app, ...)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DanmuApp


@dataclass(frozen=True)
class GenerationPipelineState:
    """诊断与状态展示用；真实所有权仍在 DanmuApp（Phase 4 冻结，勿迁入本 dataclass 写路径）。"""

    latest_displayed_round: int = 0
    latest_requested_screenshot_id: int = 0
    latest_queued_screenshot_id: int = 0
    latest_displayed_screenshot_id: int = 0

    @classmethod
    def from_app(cls, app: "DanmuApp") -> "GenerationPipelineState":
        return cls(
            latest_displayed_round=int(getattr(app, "_latest_displayed_round", 0) or 0),
            latest_requested_screenshot_id=int(
                getattr(app, "_latest_requested_screenshot_id", 0) or 0
            ),
            latest_queued_screenshot_id=int(
                getattr(app, "_latest_queued_screenshot_id", 0) or 0
            ),
            latest_displayed_screenshot_id=int(
                getattr(app, "_latest_displayed_screenshot_id", 0) or 0
            ),
        )
