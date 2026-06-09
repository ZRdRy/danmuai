"""Compatibility facade for scene brief memory (see app.memory package)."""

from app.memory import (
    SceneBriefStore,
    bullet_angle_from_index,
    clamp_prompt_dedup_window,
    prompt_dedup_window_from_config,
    truncate_scene_brief,
)
from app.memory.types import MAX_BULLET_SNIPPET_LEN
from app.memory_prompt_builder import (
    append_blocks_to_user_pt,
    build_prompt_dedup_block,
    build_scene_brief_block,
)

# Legacy alias
SceneMemoryStore = SceneBriefStore
MAX_SNIPPET_LEN = MAX_BULLET_SNIPPET_LEN
append_memory_to_user_pt = append_blocks_to_user_pt

__all__ = [
    "SceneBriefStore",
    "SceneMemoryStore",
    "append_blocks_to_user_pt",
    "append_memory_to_user_pt",
    "build_prompt_dedup_block",
    "build_scene_brief_block",
    "bullet_angle_from_index",
    "clamp_prompt_dedup_window",
    "prompt_dedup_window_from_config",
    "truncate_scene_brief",
    "MAX_SNIPPET_LEN",
]
