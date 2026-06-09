"""In-process scene brief + prompt dedup store (not persisted across sessions)."""

from __future__ import annotations

from app.memory.bullet_dedup import BulletDedupMemory
from app.memory.types import truncate_scene_brief
from app.memory_prompt_builder import build_prompt_dedup_block, build_scene_brief_block


class SceneBriefStore:
    """Holds the latest scene_brief and prompt-layer dedup window."""

    def __init__(self) -> None:
        self._brief = ""
        self._dedup = BulletDedupMemory()

    @property
    def dedup(self) -> BulletDedupMemory:
        return self._dedup

    def get_brief(self) -> str:
        return self._brief

    def set_brief(self, text: str, *, lang: str = "zh") -> None:
        self._brief = truncate_scene_brief(text, lang=lang)

    def reset(self) -> None:
        self._brief = ""
        self._dedup.clear()

    def record_displayed_bullet(
        self,
        content: str,
        *,
        window: int = 10,
        angle: str = "",
    ) -> None:
        self._dedup.record(content, angle=angle, window=window)

    def format_scene_brief_block(self) -> str:
        return build_scene_brief_block(self._brief)

    def format_prompt_dedup_block(self) -> str:
        return build_prompt_dedup_block(self._dedup)
