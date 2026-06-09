"""In-process scene brief + prompt dedup (not persisted)."""

from app.memory.store import SceneBriefStore
from app.memory.types import (
    DEFAULT_PROMPT_DEDUP_WINDOW,
    DEFAULT_SCENE_MEMORY_INTERVAL_SEC,
    MAX_BULLET_SNIPPET_LEN,
    SCENE_BRIEF_MAX_LEN_EN,
    SCENE_BRIEF_MAX_LEN_ZH,
    SCENE_MEMORY_INTERVAL_MULTIPLIER_MAX,
    bullet_angle_from_index,
    clamp_prompt_dedup_window,
    prompt_dedup_window_from_config,
    scene_memory_interval_from_config,
    scene_memory_tick_multiplier,
    snap_scene_memory_interval_sec,
    truncate_scene_brief,
)

__all__ = [
    "SceneBriefStore",
    "DEFAULT_PROMPT_DEDUP_WINDOW",
    "DEFAULT_SCENE_MEMORY_INTERVAL_SEC",
    "MAX_BULLET_SNIPPET_LEN",
    "SCENE_BRIEF_MAX_LEN_EN",
    "SCENE_BRIEF_MAX_LEN_ZH",
    "SCENE_MEMORY_INTERVAL_MULTIPLIER_MAX",
    "bullet_angle_from_index",
    "clamp_prompt_dedup_window",
    "prompt_dedup_window_from_config",
    "scene_memory_interval_from_config",
    "scene_memory_tick_multiplier",
    "snap_scene_memory_interval_sec",
    "truncate_scene_brief",
]
