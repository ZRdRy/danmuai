"""Compatibility facade for scene memory (see app.memory package).

历史说明：早期记忆实现集中在 ``app/scene_memory.py``；重构后拆分为 ``app/memory/``
子包（store/scene_context/bullet_dedup/types/visual_update）。
本文件**仅**作为 re-export 兼容层，供老 import 路径（``from app.scene_memory import
SceneMemoryStore``）继续工作。**新代码应直接导入 ``app.memory``**。
"""

from app.memory import (
    SceneMemoryStore,
    VisualMemoryUpdate,
    bullet_angle_from_index,
    clamp_memory_window,
    memory_window_from_config,
)
from app.memory.types import MAX_BULLET_SNIPPET_LEN
from app.memory_prompt_builder import append_memory_to_user_pt, build_memory_prompt_block

# Legacy alias
MAX_SNIPPET_LEN = MAX_BULLET_SNIPPET_LEN

__all__ = [
    "SceneMemoryStore",
    "VisualMemoryUpdate",
    "append_memory_to_user_pt",
    "build_memory_prompt_block",
    "bullet_angle_from_index",
    "clamp_memory_window",
    "memory_window_from_config",
    "MAX_SNIPPET_LEN",
]
