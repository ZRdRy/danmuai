from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor, QPixmap

if TYPE_CHECKING:
    from app.danmu_engine import DanmuEngine

_ENTRY_ZONE_PX_FALLBACK = 300.0


@dataclass
class DanmuItem:
    """单条弹幕条目，包含位置、速度、可见性与渲染缓存状态。"""

    content: str
    persona: str = ""
    color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    x: float = 0.0
    y: float = 0.0
    speed: float = 3.0
    width: float = 0.0
    batch_id: int = 0
    scene_generation: int = 0
    _pixmap: QPixmap | None = field(default=None, repr=False, compare=False)
    _opacity_cache_bucket: int | None = field(default=None, repr=False, compare=False)
    _cached_opacity: float | None = field(default=None, repr=False, compare=False)
    _vis_on_screen: bool = field(default=False, repr=False, compare=False)
    _right_vis_on_screen: bool = field(default=False, repr=False, compare=False)
    _in_fade_zone: bool = field(default=False, repr=False, compare=False)


class Track:
    """单条水平轨道：持有该行 DanmuItem，并维护入口区密度与更新。"""

    def __init__(self, y: float):
        self.y = y
        self.items: list[DanmuItem] = []

    def can_accept(self, item: DanmuItem, screen_width: float, min_gap: float = 150.0) -> bool:
        if not self.items:
            return True
        last = self.items[-1]
        w = last.width if last.width > 0 else (len(last.content) * 25.0)
        return last.x + w + min_gap < screen_width

    def entry_zone_count(
        self,
        screen_width: float,
        zone: float = _ENTRY_ZONE_PX_FALLBACK,
    ) -> int:
        zone_left = screen_width - zone
        return sum(1 for it in self.items if it.x + it.width > zone_left and it.x < screen_width)

    def rightmost_edge(self) -> float:
        if not self.items:
            return float("-inf")
        return max(it.x + (it.width if it.width > 0 else len(it.content) * 25.0) for it in self.items)

    def add(self, item: DanmuItem):
        item.y = self.y
        self.items.append(item)

    def update(self, speed_factor: float, dt_sec: float, engine: "DanmuEngine"):
        scale = dt_sec / (1.0 / 60.0)
        i = 0
        while i < len(self.items):
            item = self.items[i]
            item.x -= item.speed * speed_factor * scale
            if item.x + item.width <= 0:
                engine._detach_item_visibility(item)
                item._pixmap = None
                self.items.pop(i)
            else:
                engine._refresh_item_visibility(item)
                i += 1

    def drop_pending(self, screen_width: float) -> int:
        kept: list[DanmuItem] = []
        dropped = 0
        for item in self.items:
            if item.x >= screen_width:
                item._pixmap = None
                dropped += 1
            else:
                kept.append(item)
        self.items = kept
        return dropped


__all__ = ["DanmuItem", "Track"]
