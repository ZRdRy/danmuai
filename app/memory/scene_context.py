"""Scene-bound context memory (not conversation history).

SceneContextMemory 描述「当前场景」的可压缩状态，供 memory_prompt_builder 注入
用户提示词；不是多轮对话历史。字段语义：
- scene_type / scene_summary：场景类型与一句话摘要
- stable_facts：跨切换可保留的事实（medium/loose 策略会筛选或继承）
- volatile_facts：仅当前代际有效，切换时通常丢弃
- open_threads：未闭合话题线（loose 最多保留 OPEN_THREADS_MAX 条）
- last_focus：上一帧视觉焦点，用于 carryover
- confidence：整体置信，影响 medium 下 stable 是否整包保留
- tone_hint：人格语气，切换场景时由 store 继承

旧场景事实可能与新画面矛盾（如从游戏切换到桌面），注入会误导模型产生「评论错位」；
stable 之所以可保留是因为它描述跨场景不变的事实（如「用户在玩XX」），而 volatile 仅对当前画面有效。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.memory.types import (
    OPEN_THREADS_MAX,
    SCENE_SUMMARY_MAX_LEN,
    STABLE_CONFIDENCE_THRESHOLD,
    STABLE_FACTS_MAX,
    VOLATILE_FACTS_MAX,
    VisualMemoryUpdate,
)


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _append_unique_capped(items: list[str], incoming: list[str], *, limit: int) -> list[str]:
    """去重追加；超限时保留尾部最新 limit 条（与 AI 多帧增量更新顺序一致）。"""
    out = list(items)
    seen = {x for x in out}
    for raw in incoming:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) > limit:
            out = out[-limit:]
    return out


@dataclass
class SceneContextMemory:
    """单场景代际的上下文卡片；scene_generation 与 DanmuApp._scene_generation 同步。"""

    scene_generation: int = 0
    scene_type: str = ""
    scene_summary: str = ""
    stable_facts: list[str] = field(default_factory=list)  # 跨场景可保留（medium/loose 筛选继承），描述不随画面变化的事实
    volatile_facts: list[str] = field(default_factory=list)  # 仅当前代际有效，场景切换时丢弃；描述对当前画面的即时观察
    open_threads: list[str] = field(default_factory=list)
    last_focus: str = ""
    confidence: float = 0.0
    tone_hint: str = ""
    updated_at: float = 0.0

    def is_empty(self) -> bool:
        return not (
            self.scene_type
            or self.scene_summary
            or self.stable_facts
            or self.volatile_facts
            or self.open_threads
            or self.last_focus
        )

    def merge_visual_update(self, update: VisualMemoryUpdate) -> None:
        """合并 AI 视觉信封：有值字段覆盖，列表类追加去重并 cap 长度。

        scene_type/summary/last_focus 为覆盖式；stable/volatile/open_threads 为追加式
        （_append_unique_capped）；confidence 只升不降，避免单次低分拉低历史置信。
        """
        # 覆盖式：AI 最新观察替代旧值，后帧比前帧更准确
        if update.scene_type:
            self.scene_type = update.scene_type.strip()
        if update.scene_summary:
            self.scene_summary = _truncate(update.scene_summary, SCENE_SUMMARY_MAX_LEN)
        # 追加式：增量累积，去重并 cap 长度，多帧视觉结果逐步丰富卡片
        if update.stable_facts:
            self.stable_facts = _append_unique_capped(
                self.stable_facts, update.stable_facts, limit=STABLE_FACTS_MAX
            )
        if update.volatile_facts:
            self.volatile_facts = _append_unique_capped(
                self.volatile_facts, update.volatile_facts, limit=VOLATILE_FACTS_MAX
            )
        if update.open_threads:
            self.open_threads = _append_unique_capped(
                self.open_threads, update.open_threads, limit=OPEN_THREADS_MAX
            )
        if update.last_focus:
            self.last_focus = _truncate(update.last_focus, SCENE_SUMMARY_MAX_LEN)
        # confidence 只升不降：单次低置信观察不应拉低历史累积的置信度
        if update.confidence > 0:
            self.confidence = max(self.confidence, min(1.0, update.confidence))
        self.updated_at = time.monotonic()

    def carryover_summary_line(self) -> str:
        """场景切换时用于 medium/loose 的单行摘要，优先级：summary > last_focus > 末条 stable。

        调用方：SceneMemoryStore.on_scene_change 的 medium/loose 分支。
        优先级 summary>focus>stable 是因为 summary 最概括、focus 次之、stable 末条最片面。
        """
        if self.scene_summary:
            return self.scene_summary
        if self.last_focus:
            return self.last_focus
        if self.stable_facts:
            return self.stable_facts[-1]
        return ""

    def filter_stable_for_medium(self) -> list[str]:
        """medium 策略保留的 stable：整包 confidence≥0.6，否则仅保留短句（≤40 字）防噪声。

        confidence≥0.6 时整包保留（已确认的事实集可信，丢弃任意一条可能丢失关键信息）；
        低于阈值时仅保留短句（≤40字），低置信时长句更可能是噪声。
        """
        if self.confidence >= STABLE_CONFIDENCE_THRESHOLD:
            return list(self.stable_facts)
        return [f for f in self.stable_facts if len(f) <= SCENE_SUMMARY_MAX_LEN]

    def reset_for_generation(
        self,
        scene_generation: int,
        *,
        tone_hint: str = "",
        scene_type: str = "",
        scene_summary: str = "",
        stable_facts: list[str] | None = None,
        volatile_facts: list[str] | None = None,
        open_threads: list[str] | None = None,
        last_focus: str = "",
        confidence: float = 0.0,
    ) -> None:
        """场景代际切换时重建卡片；由 SceneMemoryStore.on_scene_change 写入保留字段。"""
        self.scene_generation = scene_generation
        self.scene_type = scene_type
        self.scene_summary = scene_summary
        self.stable_facts = list(stable_facts or [])
        self.volatile_facts = list(volatile_facts or [])
        self.open_threads = list(open_threads or [])
        self.last_focus = last_focus
        self.confidence = confidence
        self.tone_hint = tone_hint
        self.updated_at = time.monotonic() if not self.is_empty() else 0.0

    def empty_clone(self, scene_generation: int, *, tone_hint: str = "") -> SceneContextMemory:
        """strict 策略等价物：新代际空卡片，仅继承 tone_hint。"""
        return SceneContextMemory(scene_generation=scene_generation, tone_hint=tone_hint)
