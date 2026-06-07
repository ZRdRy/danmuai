"""Format activity state as a single-line prompt injection.

仅在 ``memory_mode == "strong"`` 模式下被 ``memory_prompt_builder`` 消费；
输出形如 ``近期状态：用户在写代码（IDE）`` 的单行，附加到用户提示词末尾。
"""

from __future__ import annotations

from app.memory.activity import RecentActivityState


def format_activity_prompt_line(state: RecentActivityState) -> str:
    if not state.activity_summary:
        return ""
    return f"近期状态：{state.activity_summary}"


def append_activity_line_to_user_pt(user_pt: str, line: str) -> str:
    if not line:
        return user_pt
    return f"{user_pt.rstrip()}\n\n{line}"
