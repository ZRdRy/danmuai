"""Tests for activity prompt formatting."""

from app.memory.activity import RecentActivityState
from app.memory.activity_prompt import (
    append_activity_line_to_user_pt,
    format_activity_prompt_line,
)


def _state_with_summary(summary: str) -> RecentActivityState:
    state = RecentActivityState()
    state.activity_summary = summary
    state.activity_type = "coding"
    return state


class TestFormatActivityPromptLine:
    def test_empty_summary_returns_empty(self):
        state = RecentActivityState()
        assert format_activity_prompt_line(state) == ""

    def test_unknown_type_empty_summary(self):
        state = RecentActivityState()
        state.activity_type = "unknown"
        assert format_activity_prompt_line(state) == ""

    def test_coding_summary(self):
        state = _state_with_summary("用户正在写代码")
        line = format_activity_prompt_line(state)
        assert line == "近期状态：用户正在写代码"

    def test_game_summary(self):
        state = RecentActivityState()
        state.activity_type = "game"
        state.activity_summary = "用户正在玩《英雄联盟》"
        line = format_activity_prompt_line(state)
        assert line == "近期状态：用户正在玩《英雄联盟》"

    def test_game_no_name(self):
        state = RecentActivityState()
        state.activity_type = "game"
        state.activity_summary = "用户正在玩一款游戏"
        line = format_activity_prompt_line(state)
        assert line == "近期状态：用户正在玩一款游戏"

    def test_no_newlines_in_output(self):
        state = _state_with_summary("用户正在写代码，并多次切换浏览器查询资料")
        line = format_activity_prompt_line(state)
        assert "\n" not in line

    def test_no_window_title_leaked(self):
        state = _state_with_summary("用户正在写代码")
        line = format_activity_prompt_line(state)
        assert "Visual Studio Code" not in line
        assert "main.py" not in line

    def test_no_exe_name_leaked(self):
        state = _state_with_summary("用户正在浏览网页")
        line = format_activity_prompt_line(state)
        assert "chrome.exe" not in line
        assert ".exe" not in line


class TestAppendActivityLineToUserPt:
    def test_empty_line_no_change(self):
        result = append_activity_line_to_user_pt("请生成弹幕：", "")
        assert result == "请生成弹幕："

    def test_appends_line(self):
        result = append_activity_line_to_user_pt("请生成弹幕：", "近期状态：用户正在写代码")
        assert result == "请生成弹幕：\n\n近期状态：用户正在写代码"

    def test_strips_trailing_whitespace_from_user_pt(self):
        result = append_activity_line_to_user_pt("请生成弹幕：  ", "近期状态：用户正在写代码")
        assert result == "请生成弹幕：\n\n近期状态：用户正在写代码"
