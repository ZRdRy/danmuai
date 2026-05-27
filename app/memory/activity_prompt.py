"""Format activity state as a single-line prompt injection."""

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
