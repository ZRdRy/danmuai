"""Pure helpers and small data types extracted from main.py (W-REFACTOR-MAIN-001).

No Qt imports and no DanmuApp dependency — safe for unit tests and scheduling logic.
"""

from __future__ import annotations

from app.danmu_engine import DanmuItem
from app.memory.types import MEMORY_MODE_OFF
from app.personae import persona_display_name

VISUAL_INFLIGHT_WARN_SEC = 45.0


class BatchTracker:
    """当前视觉批次的锚点元数据（普通模式）。

    anchor_item：本批首条成功上屏弹幕；滚到屏幕 75% 宽处时写入 next_generation_time，
    供 API 调度 debug 日志（_log_api_schedule）与批次观测，不驱动额外截图定时器。
    """

    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        self.anchor_item: DanmuItem | None = None
        self.next_generation_time: float = 0.0


def reply_request_id(request_round: int, screenshot_id: int, scene_generation: int) -> str:
    return f"{request_round}:{screenshot_id}:{scene_generation}"


def density_right_target(min_n: int) -> int:
    if min_n <= 0:
        return 2
    return max(1, min_n // 3)


def scene_api_block_reason() -> str:
    return ""


def scene_api_blocked() -> bool:
    return bool(scene_api_block_reason())


def is_reply_stale(
    screenshot_id: int,
    captured_at: float,
    scene_generation: int,
    *,
    source: str = "ai",
) -> tuple[bool, str]:
    """普通模式与 mic：当前均不做过期回复硬丢弃。

    产品策略：不比较 screenshot_id / captured_at TTL / scene_generation 来丢弃在途或
    队列中的回复；慢模型下允许轻微滞后，优先保证弹幕连续性。
    保留为 _on_ai_reply / _consume_reply_queue 的兼容调用点及未来策略扩展入口；
    当前固定返回 (False, "")。
    """
    del screenshot_id, captured_at, scene_generation, source
    return False, ""


def memory_tone_hint(persona_id: str) -> str:
    if not persona_id:
        return ""
    return persona_display_name(persona_id)


def memory_mode_from_value(raw: object) -> str:
    value = raw if raw else MEMORY_MODE_OFF
    return str(value).strip().lower()


def memory_enabled(mode: str) -> bool:
    return mode != MEMORY_MODE_OFF


def queue_capacity(normal_reply_count: int) -> int:
    return max(8, normal_reply_count * 2)
