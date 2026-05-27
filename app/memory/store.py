"""Scene memory store: context + bullet dedup.

SceneMemoryStore 是记忆子系统的门面，组合 SceneContextMemory（场景卡片）与
BulletDedupMemory（近期弹幕去重）。纯内存、随 DanmuApp 会话生命周期，不写 SQLite。

注意：activity（活跃度/截图退避等）由 DanmuApp 直接持有，不在 store 内组合；
store 只负责 context + dedup 两块。

四档 memory_mode（在 format_prompt_for_generation → build_memory_prompt_block 生效）：
- off：不注入记忆提示词
- dedup_only：仅弹幕去重段，字符预算最小
- scene_card：语气 + 场景状态卡片（默认）
- strong：更高字符预算；medium 切换时若无 stable 可保留 carryover 摘要行

三档场景清除策略 on_scene_change(policy)（与 drop_stale 配置对应，由 main 传入）：
- strict：新建空 context，dedup 全清
- medium：仅保留高置信 stable_facts（及 strong 下的 carryover），dedup 全清
- loose：继承 summary/stable/open_threads，dedup 仅 trim 最近几条

调用链：
  format_prompt_for_generation → build_memory_prompt_block → append_memory_to_user_pt → AiWorker._request
"""

from __future__ import annotations

from app.memory.bullet_dedup import BulletDedupMemory
from app.memory.scene_context import SceneContextMemory
from app.memory.types import (
    INFERRED_CONFIDENCE,
    OPEN_THREADS_MAX,
    STABLE_CONFIDENCE_THRESHOLD,
    VisualMemoryUpdate,
)


class SceneMemoryStore:
    """场景记忆门面：context（视觉卡片）+ dedup（已播弹幕窗口）。

    generation 与 DanmuApp._scene_generation 对齐；代际不一致的写入/读提示词均静默忽略，
    避免场景切换后迟到的 AI 视觉结果污染新场景或提示词块错位。
    """

    def __init__(self) -> None:
        self._context = SceneContextMemory(scene_generation=0)
        self._dedup = BulletDedupMemory()

    @property
    def context(self) -> SceneContextMemory:
        return self._context

    @property
    def dedup(self) -> BulletDedupMemory:
        return self._dedup

    @property
    def generation(self) -> int:
        return self._context.scene_generation

    def reset(self) -> None:
        self._context = SceneContextMemory(scene_generation=0)
        self._dedup.clear()

    def update_from_visual_result(self, update: VisualMemoryUpdate) -> None:
        """将 AI 回复信封中的 scene_memory 合并进当前代际 context。

        代际不匹配时静默 return：截图→请求在途期间画面可能已切换，旧代际的视觉更新
        若写入会覆盖新场景卡片，故只接受与 self.generation 一致的 update。
        """
        if update.scene_generation != self._context.scene_generation:
            return
        self._context.merge_visual_update(update)

    def record_displayed_bullet(
        self,
        content: str,
        scene_generation: int,
        *,
        window: int = 10,
        angle: str = "",
    ) -> None:
        """记录一条已上屏弹幕，供 dedup 提示与引擎去重协同。

        代际不匹配时静默 return，避免旧场景弹幕写入新代际 dedup 窗口。
        """
        if scene_generation != self._context.scene_generation:
            return
        self._dedup.record(content, angle=angle, window=window)

    def on_scene_change(
        self,
        new_generation: int,
        policy: str,
        *,
        tone_hint: str = "",
        memory_window: int = 10,
        memory_mode: str = "scene_card",
    ) -> None:
        """场景代际升高时按 policy 迁移 context 并整理 dedup。

        strict：彻底重置，适合用户要求「一切跟当前画面」、不保留旧场景事实。
        medium：保留 filter_stable_for_medium() 筛出的 stable；strong 且无 stable 时用
        carryover_summary_line 作为单条 stable（INFERRED_CONFIDENCE）；dedup 全清。
        loose：summary/stable/open_threads/last_focus 尽量延续，dedup trim 至 min(3, window)。
        memory_mode 仅影响 medium 分支是否在无 stable 时注入 carryover。
        """
        prev = self._context
        preserved_tone = tone_hint or prev.tone_hint
        policy = (policy or "medium").strip().lower()

        # strict：彻底重置——用户要求一切跟当前画面，不保留旧场景任何事实；
        # volatile/open_threads 不继承，dedup 清空，避免旧画面事实进入新代际提示词
        if policy == "strict":
            self._context = SceneContextMemory(
                scene_generation=new_generation,
                tone_hint=preserved_tone,
            )
            self._dedup.clear()
            return

        # medium：保留高置信 stable——避免丢失已确认的跨场景事实，但 volatile/open_threads 不继承；
        # volatile 丢弃；stable 经置信筛选；strong 无 stable 时用 carryover 单行兜底
        if policy == "medium":
            stable = prev.filter_stable_for_medium()
            if (
                memory_mode == "strong"
                and not stable
                and prev.carryover_summary_line()
            ):
                stable = [prev.carryover_summary_line()]
                conf = INFERRED_CONFIDENCE
            else:
                conf = prev.confidence if stable else 0.0
            self._context.reset_for_generation(
                new_generation,
                tone_hint=preserved_tone,
                stable_facts=stable,
                confidence=conf,
            )
            self._dedup.clear()
            return

        # loose：延续摘要/stable/threads——适合慢切换场景，保留上下文连贯性；
        # summary/stable/open_threads/last_focus 尽量延续；dedup 仅留最近几条减轻「换场景仍复读旧弹幕」
        carry = prev.carryover_summary_line()
        stable = list(prev.stable_facts) or (
            [carry] if carry and prev.confidence >= STABLE_CONFIDENCE_THRESHOLD else []
        )
        threads = list(prev.open_threads[-OPEN_THREADS_MAX:])
        self._context.reset_for_generation(
            new_generation,
            tone_hint=preserved_tone,
            scene_summary=carry,
            stable_facts=stable,
            open_threads=threads,
            last_focus=prev.last_focus if prev.last_focus else carry,
            confidence=prev.confidence if stable else INFERRED_CONFIDENCE,
        )
        # 最多 3 条：loose 仍要一点近期措辞去重，但不宜带太多旧场景 bullet
        keep_bullets = min(3, memory_window) if memory_window > 0 else 0
        self._dedup.trim_to(keep_bullets)

    def format_prompt_for_generation(
        self,
        scene_generation: int,
        memory_mode: str,
    ) -> str:
        """为当前 AI 请求组装记忆提示词块；代际不匹配返回空串。

        调用方（main）传入的 scene_generation 必须与 store.generation 一致，
        否则说明请求绑定的是旧场景，注入记忆会误导模型。

        调用链：此方法返回的文本 → build_memory_prompt_block() →
        append_memory_to_user_pt() → 拼入 user_pt → AiWorker._request() 作为用户提示词的一部分
        """
        if scene_generation != self._context.scene_generation:
            return ""
        from app.memory_prompt_builder import build_memory_prompt_block

        return build_memory_prompt_block(self._context, self._dedup, memory_mode)
