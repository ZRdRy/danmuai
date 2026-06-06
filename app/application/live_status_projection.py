"""Live status 纯只读投影（无 Qt 导入、无状态修改）。

从 DanmuApp 提取的纯计算逻辑：当前弹幕延迟、live status 快照组装。
"""

from __future__ import annotations

import time

from app.live_freshness import LiveStatusSnapshot
from app.reply_queue import AIReplyFIFOBuffer


def current_danmu_delay_sec(
    has_visual_request_in_flight: bool,
    inflight_started_at: float,
    reply_buffer: AIReplyFIFOBuffer,
    latest_screenshot_time: float,
) -> float:
    """计算当前弹幕延迟（秒）。"""
    if has_visual_request_in_flight and inflight_started_at > 0:
        return max(0.0, time.monotonic() - inflight_started_at)
    head = reply_buffer.peek()
    if head and head.captured_at > 0:
        return max(0.0, time.monotonic() - head.captured_at)
    if latest_screenshot_time > 0:
        return max(0.0, time.monotonic() - latest_screenshot_time)
    return 0.0


def build_live_status_snapshot(
    has_visual_request_in_flight: bool,
    inflight_started_at: float,
    reply_buffer: AIReplyFIFOBuffer,
    latest_screenshot_time: float,
    *,
    local_fallback: bool = False,
) -> LiveStatusSnapshot:
    """组装 LiveStatusSnapshot。"""
    return LiveStatusSnapshot(
        analyzing=has_visual_request_in_flight,
        local_fallback=local_fallback,
        delay_sec=current_danmu_delay_sec(
            has_visual_request_in_flight,
            inflight_started_at,
            reply_buffer,
            latest_screenshot_time,
        ),
    )
