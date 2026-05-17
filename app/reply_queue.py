from dataclasses import dataclass
from collections import deque


@dataclass(frozen=True)
class QueuedReply:
    persona_id: str
    batch_index: int
    content_index: int
    content: str
    screenshot_round: int = 0
    screenshot_id: int = 0
    captured_at: float = 0.0
    scene_generation: int = 0
    batch_id: int = 0


class AIReplyFIFOBuffer:
    def __init__(self, max_items: int = 8):
        self._items = deque()
        self._max_items = max_items

    def push(self, item: QueuedReply):
        if item.scene_generation > 0:
            self.drop_older_generations(item.scene_generation)
        self._items.append(item)
        while len(self._items) > self._max_items:
            self._items.popleft()

    def pop(self) -> QueuedReply | None:
        if not self._items:
            return None
        return self._items.popleft()

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

    def prepend_batch(
        self,
        items: list[QueuedReply],
        preserve_existing: int = 0,
        preserve_scene_generation: int | None = None,
    ):
        preserved: list[QueuedReply] = []
        if preserve_existing > 0:
            for item in self._items:
                if preserve_scene_generation is not None and item.scene_generation != preserve_scene_generation:
                    continue
                preserved.append(item)
                if len(preserved) >= preserve_existing:
                    break

        self._items = deque([*items, *preserved])
        while len(self._items) > self._max_items:
            self._items.pop()

    def purge_before_round(self, min_round: int):
        self._items = deque(
            item for item in self._items if item.screenshot_round >= min_round
        )

    def drop_older_generations(self, min_generation: int):
        self._items = deque(
            item for item in self._items if item.scene_generation >= min_generation
        )
