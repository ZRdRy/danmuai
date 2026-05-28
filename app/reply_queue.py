"""AI 回复弹幕的有序 FIFO 缓冲（由 main.DanmuApp 持有并消费）。

队列存在的根本原因：AI 请求延迟不可预测（数百毫秒到数秒），而弹幕上屏需要有序、
不过期、不积压。队列在「AI 异步返回」与「主线程定时消费」之间做缓冲与过滤，
保证消费端 pop 出来的每条弹幕都是当前场景下有效的。

主流程位置：
- 写入：DanmuApp._enqueue_reply_batch() → push / prepend_batch
- 消费：DanmuApp._consume_reply_queue() → pop，由 reply_timer 或主循环主动触发
- 场景切换：_on_scene_generation_advanced() → drop_older_generations / prepend_batch
- AI 回复到达：_on_ai_reply() → 先 drop_replaceable_fallbacks 清理兜底，再 prepend_batch

三种核心队列语义：
1. **入队 push**：按到达顺序追加；超出 max_items 时从队首丢弃最旧条目。
2. **代际淘汰**：新场景（scene_generation 升高）到达时，丢弃更低代际的待播回复——
   画面已切换，旧场景弹幕内容与当前画面不再相关。
3. **fallback 替换**：本地轻量兜底弹幕（replaceable=True）可被同批次的 AI 回复顶掉——
   兜底来自弹幕池/硬编码，质量低于模型生成；AI 回复到达时不应再占消费顺序与轨道。

这不是普通 FIFO：代际淘汰和 fallback 替换使队列具有「优先级过滤」语义，
而非简单的先进先出。
"""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class QueuedReply:
    """单条待上屏弹幕及其批次/场景元数据（不可变，便于在队列间传递）。"""

    persona_id: str  # 人格 id，决定弹幕样式与记忆 tone
    batch_index: int  # 请求轮次内的批次序号（历史/日志用）
    content_index: int  # 批次内第几条，用于记忆角度 bullet_angle_from_index
    content: str  # 弹幕正文（展示前可能再经 normalize_danmu_display_text）
    screenshot_round: int = 0  # 调度轮次（粗粒度），入队时从 DanmuApp.screenshot_round 复制；purge_before_round 按此淘汰
    screenshot_id: int = 0  # 逐帧递增 id（细粒度），入队时从 _latest_screenshot_id 复制；_is_reply_stale 据此判断回复是否基于过时截图
    captured_at: float = 0.0  # 截图 monotonic 时间戳，TTL 新鲜度判断
    scene_generation: int = 0  # 入队时从 _scene_generation 复制；drop_older_generations / prepend_batch(preserve_scene_generation) 读取；场景切换后旧代际弹幕与画面不匹配必须丢弃
    batch_id: int = 0  # 入队时从 _batch_id 复制；drop_replaceable_fallbacks 按 batch_id 匹配可替换兜底；trigger_acceleration 按批次锚点加速
    request_id: str = ""  # 同轮 AI 请求唯一键；同一 batch 可有多轮 mic 请求，request_id 区分视觉 vs 麦克风来源；drop_replaceable_fallbacks 按此匹配
    is_fallback: bool = False  # True=本地轻量兜底批次，非模型输出
    source: str = "ai"  # ai | fallback | mic；_consume_reply_queue 读取：mic 跳过去重、fallback 不写 scene_memory
    replaceable: bool = False  # True 且 source=fallback 时，可被同 request_id/batch_id 的 AI 批次替换
    memory_eligible: bool = True  # False 时不上报 scene_memory（兜底通常 False）


class AIReplyFIFOBuffer:
    """有序 FIFO 缓冲：先入先出消费，容量有界（默认 max_items=8）。

    在 DanmuApp 主循环中缓冲 AI/兜底/麦克风插入批次，与场景代际淘汰、
    replaceable fallback 清理配合，避免过期或低质量条目阻塞高质量回复。
    """

    def __init__(self, max_items: int = 8):
        self._items = deque()
        self._max_items = max_items  # 容量上界：太小则场景切换后无弹幕可播，太大则积压导致消费延迟；默认 8 平衡两者

    def push(self, item: QueuedReply):
        """追加一条到队尾；若 item.scene_generation>0，先淘汰所有更低代际条目再入队。

        先淘汰再入队，保证新条目入队后队列中不会残留旧代际条目，
        避免消费端 pop 到与当前画面不匹配的过期弹幕。
        """
        if item.scene_generation > 0:
            self.drop_older_generations(item.scene_generation)
        self._items.append(item)
        # 容量有界：丢弃队首最旧，防止 AI 连发时积压过多过期弹幕
        while len(self._items) > self._max_items:
            self._items.popleft()

    def pop(self) -> QueuedReply | None:
        """FIFO 队首取出一条，供 _consume_reply_queue 上屏。"""
        if not self._items:
            return None
        return self._items.popleft()

    def peek(self) -> QueuedReply | None:
        if not self._items:
            return None
        return self._items[0]

    def clear(self):
        self._items.clear()

    def is_empty(self) -> bool:
        return not self._items

    def size(self) -> int:
        return len(self._items)

    def set_max_items(self, max_items: int):
        self._max_items = max(1, max_items)
        while len(self._items) > self._max_items:
            self._items.pop()

    def extend(self, items: list[QueuedReply]):
        """批量 push，每条仍走代际淘汰与容量裁剪。"""
        for item in items:
            self.push(item)

    def prepend_batch(
        self,
        items: list[QueuedReply],
        preserve_existing: int = 0,
        preserve_scene_generation: int | None = None,
        preserve_replaceable: bool = True,
    ):
        """场景切换、麦克风或本地兜底插入时，新批次插在队首而非 append。

        与 push 的区别：push 追加到队尾（正常 AI 回复），prepend_batch 插到队首
        （新场景弹幕应优先消费）。超长裁剪方向也不同：push 从队首丢（旧优先丢弃），
        prepend 从队尾丢（新批次优先保留）。

        消费端 pop 从队首取，prepend 使新场景或刚生成的兜底优先上屏；
        同时可按参数保留队中前 N 条「仍有效」的旧条目接在后面。
        preserve_existing: 最多保留队首侧连续匹配的条数（0=不保留）。
        preserve_scene_generation: 非 None 时只保留该 scene_generation 的条目。
        preserve_replaceable: False 时跳过 replaceable 条目（AI 入队前常清掉可替换兜底）。
        """
        preserved: list[QueuedReply] = []
        if preserve_existing > 0:
            for item in self._items:
                if preserve_scene_generation is not None and item.scene_generation != preserve_scene_generation:
                    continue
                if not preserve_replaceable and item.replaceable:
                    continue
                preserved.append(item)
                if len(preserved) >= preserve_existing:
                    break

        self._items = deque([*items, *preserved])
        # prepend 后超长从队尾 pop（保留队首新批次优先消费）
        while len(self._items) > self._max_items:
            self._items.pop()

    def drop_replaceable_fallbacks(
        self,
        *,
        request_id: str = "",
        batch_id: int | None = None,
        scene_generation: int | None = None,
    ) -> int:
        """移除可被 AI 顶掉的本地 fallback，返回删除条数。

        仅删除 is_fallback 且 replaceable 且 source==fallback 的条目。
        scene_generation 非 None 时需与条目代际一致。
        匹配条件（满足其一即可）：request_id 非空且与条目相同，或 batch_id 非 None 且与条目相同。
        设计意图：可替换兜底不占长期队列槽位，同批 AI 回复 prepend 后优先消费。
        """
        before = len(self._items)
        self._items = deque(
            item
            for item in self._items
            if not (
                item.is_fallback
                and item.replaceable
                and item.source == "fallback"
                and (scene_generation is None or item.scene_generation == scene_generation)
                and (
                    (request_id and item.request_id == request_id)
                    or (batch_id is not None and item.batch_id == batch_id)
                )
            )
        )
        return before - len(self._items)

    def purge_before_round(self, min_round: int):
        """丢弃 screenshot_round 早于 min_round 的条目（调度轮次回退或重置时用）。"""
        self._items = deque(
            item for item in self._items if item.screenshot_round >= min_round
        )

    def drop_older_generations(self, min_generation: int):
        """丢弃 scene_generation < min_generation 的条目。

        新场景到达后旧代际弹幕与当前画面无关，继续消费会造成「评论错位」。
        """
        self._items = deque(
            item for item in self._items if item.scene_generation >= min_generation
        )
