"""In-process scene state + bullet dedup memory (not persisted).

记忆模块整体架构（与四档 ``memory_mode`` 配合）：
- ``off``：关闭记忆，不向 AI 提示词注入任何记忆块。
- ``dedup_only``：仅注入弹幕去重段（已播文本/角度），引导 AI 换角度。
- ``scene_card``：场景卡片 + 去重段，**默认**档（覆盖多数普通直播）。
- ``strong``：场景 + 活动 + 去重，字符预算最大（``BUDGET_STRONG=700``）。

子模块职责：
- ``store``：门面 ``SceneMemoryStore``，组合 context + dedup。
- ``scene_context``：场景卡片状态（scene_type/summary/stable/volatile/open_threads/focus/tone）。
- ``activity``：前台窗口活动追踪（不是弹幕内容）。
- ``bullet_dedup``：弹幕去重（prompt 层），与 ``danmu_engine`` 的渲染层去重协同。
- ``visual_update``：解析 AI ``scene_memory`` 信封，构造 ``VisualMemoryUpdate``。
- ``types``：常量与 dataclass（``MEMORY_MODES``、``clamp_memory_window`` 等）。
- ``activity_prompt``：活动状态 → 单行 prompt 注入文本。

约束：纯内存、不写 SQLite；随 ``DanmuApp`` 会话生命周期。
"""

from app.memory.store import SceneMemoryStore
from app.memory.types import (
    MAX_BULLET_SNIPPET_LEN,
    MEMORY_MODES,
    VisualMemoryUpdate,
    bullet_angle_from_index,
    clamp_memory_window,
    memory_window_from_config,
)

__all__ = [
    "SceneMemoryStore",
    "VisualMemoryUpdate",
    "MEMORY_MODES",
    "MAX_BULLET_SNIPPET_LEN",
    "bullet_angle_from_index",
    "clamp_memory_window",
    "memory_window_from_config",
]
