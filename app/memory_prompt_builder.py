"""记忆提示词组装器：将 SceneContextMemory + BulletDedupMemory 拼成结构化文本块，注入 AI 用户提示词。

独立模块原因：prompt 组装涉及字符预算分配、section 排序、mode 分支，放在 main.py 会加剧上帝类膨胀。

调用链：SceneMemoryStore.format_prompt_for_generation() → build_memory_prompt_block() → append_memory_to_user_pt() → DanmuApp._build_user_pt()

字符预算（与四档 memory_mode 对应，见 BUDGET_* 常量）：
- BUDGET_DEDUP_ONLY = 220
- BUDGET_SCENE_CARD = 450（默认 scene_card 档）
- BUDGET_STRONG = 700（强记忆档，容纳 carryover 摘要 + 更多 stable facts）

约束：模块不导入 Qt，不持有线程状态；可在主线程任何位置安全调用。
"""

from __future__ import annotations

from app.memory.bullet_dedup import BulletDedupMemory
from app.memory.scene_context import SceneContextMemory
from app.memory.types import MEMORY_MODE_DEDUP_ONLY, MEMORY_MODE_STRONG

BUDGET_DEDUP_ONLY = 220  # 仅去重段，字符预算最小
BUDGET_SCENE_CARD = 450  # 默认：场景状态 + 去重 + 约束
BUDGET_STRONG = 700  # 更大预算，容纳 carryover 摘要和更多 stable facts

_CONFLICT_LINE = "必须以当前截图为最高优先级；以上记忆仅作辅助，冲突时忽略记忆。"


def _join_list(items: list[str], sep: str = "；") -> str:
    return sep.join(x for x in items if x)


def build_scene_state_section(ctx: SceneContextMemory) -> str:
    """场景状态段：输出场景类型/摘要/stable/volatile/threads/focus/tone；context 为空或无 tone_hint 时返回空块。"""
    if ctx.is_empty() and not ctx.tone_hint:
        return ""
    lines = ["【当前场景状态】"]
    if ctx.scene_type:
        lines.append(f"类型：{ctx.scene_type}")
    if ctx.scene_summary:
        lines.append(f"摘要：{ctx.scene_summary}")
    if ctx.stable_facts:
        lines.append(f"稳定事实：{_join_list(ctx.stable_facts)}")
    if ctx.volatile_facts:
        lines.append(f"易变事实：{_join_list(ctx.volatile_facts)}")
    if ctx.open_threads:
        lines.append(f"未闭合线索：{_join_list(ctx.open_threads)}")
    if ctx.last_focus:
        lines.append(f"当前焦点：{ctx.last_focus}")
    if ctx.tone_hint:
        lines.append(f"语气提示：{ctx.tone_hint}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def build_dedup_section(dedup: BulletDedupMemory) -> str:
    """去重提示段：输出最近上屏弹幕/已用角度/避免角度；无记录时返回空块。"""
    if dedup.is_empty():
        return ""
    lines = ["【最近弹幕去重】"]
    texts = [b.text for b in dedup.recent_bullets[-5:]]
    if texts:
        lines.append(f"最近上屏：{_join_list(texts)}")
    if dedup.recent_angles:
        lines.append(f"已用表达角度：{_join_list(dedup.recent_angles)}")
    if dedup.avoid_angles:
        lines.append(f"下轮避免角度：{_join_list(dedup.avoid_angles)}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def build_constraints_section() -> str:
    """约束声明段：输出冲突优先级声明和生成约束。"""
    return "\n".join(
        [
            "【生成约束】",
            f"- {_CONFLICT_LINE}",
            "- 不要重复最近已用的表达角度与句式。",
            "- 每条弹幕仍需遵守人格输出契约。",
        ]
    )


def _budget_for_mode(memory_mode: str) -> int:
    if memory_mode == MEMORY_MODE_STRONG:
        return BUDGET_STRONG
    if memory_mode == MEMORY_MODE_DEDUP_ONLY:
        return BUDGET_DEDUP_ONLY
    return BUDGET_SCENE_CARD


def _trim_to_budget(parts: list[str], budget: int) -> str:
    """按字符预算裁剪：约束段不可裁剪（安全声明），body 段超长时截断并加「...」。"""
    block = "\n\n".join(p for p in parts if p)
    if len(block) <= budget:
        return block
    constraints = build_constraints_section()
    if len(constraints) >= budget:
        return constraints[:budget]
    remaining = budget - len(constraints) - 2
    body_parts = [p for p in parts if p and p != constraints]
    body = "\n\n".join(body_parts)
    if len(body) > remaining:
        body = body[: max(0, remaining - 3)] + "..."
    return f"{body}\n\n{constraints}" if body else constraints


def build_memory_prompt_block(
    ctx: SceneContextMemory,
    dedup: BulletDedupMemory,
    memory_mode: str,
) -> str:
    mode = (memory_mode or "off").strip().lower()
    # off 模式：不注入任何记忆提示词
    if mode == "off":
        return ""

    constraints = build_constraints_section()
    dedup_sec = build_dedup_section(dedup)

    # dedup_only：仅拼去重段 + 约束，字符预算最小
    if mode == MEMORY_MODE_DEDUP_ONLY:
        parts = [p for p in (dedup_sec, constraints) if p]
        return _trim_to_budget(parts, _budget_for_mode(mode))

    # scene_card / strong：拼场景状态 + 去重 + 约束，strong 预算更大
    scene_sec = build_scene_state_section(ctx)
    parts = [p for p in (scene_sec, dedup_sec, constraints) if p]
    return _trim_to_budget(parts, _budget_for_mode(mode))


def append_memory_to_user_pt(user_pt: str, block: str) -> str:
    """将记忆块追加到用户提示词末尾；由 DanmuApp._build_user_pt 调用。"""
    if not block:
        return user_pt
    return f"{user_pt.rstrip()}\n\n{block}"
