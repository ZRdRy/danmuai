"""会话内统计的真实所有者；DanmuApp.danmu_count 等 @property 仅为旧代码兼容 façade。"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class StatsState:
    """Boundary Guard 禁止在 DanmuApp 新增对 danmu_count / _total_*_tokens 的直接写入。"""

    danmu_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    start_time: float = 0.0

    def reset_session(self, *, start_time: float) -> None:
        self.danmu_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.start_time = float(start_time)

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.total_input_tokens += int(input_tokens or 0)
        self.total_output_tokens += int(output_tokens or 0)

    def add_danmu(self, count: int = 1) -> None:
        self.danmu_count += int(count or 0)

    def runtime_sec(self, now: float | None = None) -> float:
        if self.start_time <= 0:
            return 0.0
        current = time.monotonic() if now is None else float(now)
        return max(0.0, current - self.start_time)

    def clear_runtime(self) -> None:
        self.start_time = 0.0
