"""Prompt blocks for scene brief and prompt-layer bullet dedup."""

from __future__ import annotations

from app.memory.bullet_dedup import BulletDedupMemory


def build_scene_brief_block(brief: str) -> str:
    """Inject last round scene brief before the next visual request."""
    text = (brief or "").strip()
    if not text:
        return ""
    return "\n".join(
        [
            "【当前场景】",
            text,
            "若与当前截图冲突，以当前截图为准。",
        ]
    )


def build_prompt_dedup_block(dedup: BulletDedupMemory) -> str:
    """Prompt-layer dedup hints; independent from scene brief."""
    if dedup.is_empty():
        return ""
    lines = ["【最近弹幕去重】"]
    texts = [b.text for b in dedup.recent_bullets[-5:]]
    if texts:
        lines.append(f"最近上屏：{'；'.join(x for x in texts if x)}")
    if dedup.recent_angles:
        lines.append(f"已用表达角度：{'；'.join(dedup.recent_angles)}")
    if dedup.avoid_angles:
        lines.append(f"下轮避免角度：{'；'.join(dedup.avoid_angles)}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def append_blocks_to_user_pt(user_pt: str, *blocks: str) -> str:
    parts = [user_pt.rstrip()] if (user_pt or "").strip() else []
    for block in blocks:
        text = (block or "").strip()
        if text:
            parts.append(text)
    if not parts:
        return user_pt or ""
    return "\n\n".join(parts)
