"""视觉 API 触发节流：拥有 last_api_trigger_at，不发起 HTTP、不消费回复队列。

禁止绕过：所有 API 触发必须经此调度器的 block_reason() 判断，不得直接检查 in_flight 或时间戳。
"""
from __future__ import annotations

from collections.abc import Callable


class RequestScheduler:
    """纯调度判断；DanmuApp._trigger_api_call 在 fire 前调用 record_trigger_time。"""

    def __init__(self, *, last_api_trigger_at: float = 0.0) -> None:
        self.last_api_trigger_at = float(last_api_trigger_at)

    def reset_trigger_time(self) -> None:
        self.last_api_trigger_at = 0.0

    def block_reason(
        self,
        *,
        has_visual_request_in_flight: bool,
        enforce_min_interval: bool,
        last_trigger_at: float | None = None,
        min_interval_elapsed: Callable[[float], bool],
    ) -> str:
        """返回阻塞原因：空串=可触发；"in_flight"=有视觉请求在途；"min_api_interval"=防连打间隔未到。"""
        trigger_at = self.last_api_trigger_at if last_trigger_at is None else float(last_trigger_at)
        if has_visual_request_in_flight:
            return "in_flight"
        if enforce_min_interval and not min_interval_elapsed(trigger_at):
            return "min_api_interval"
        return ""

    def can_trigger(
        self,
        *,
        has_visual_request_in_flight: bool,
        enforce_min_interval: bool,
        last_trigger_at: float | None = None,
        min_interval_elapsed: Callable[[float], bool],
    ) -> bool:
        return (
            self.block_reason(
                has_visual_request_in_flight=has_visual_request_in_flight,
                enforce_min_interval=enforce_min_interval,
                last_trigger_at=last_trigger_at,
                min_interval_elapsed=min_interval_elapsed,
            )
            == ""
        )

    def record_trigger_time(
        self,
        *,
        now: float,
        set_last_trigger_at: Callable[[float], None] | None = None,
    ) -> float:
        trigger_at = float(now)
        self.last_api_trigger_at = trigger_at
        if set_last_trigger_at is not None:
            set_last_trigger_at(trigger_at)
        return trigger_at
