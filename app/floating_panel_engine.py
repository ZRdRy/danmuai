"""侧边悬浮窗弹幕引擎：底部进入后持续上滚，越顶即移除。

W-FP-V3-002：修复 V2 的“堆叠停留 + 固定写死速度”语义，改为接线
``floating_panel_speed`` 的持续向上滚动模型。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.danmu_engine import normalize_danmu_display_text

if TYPE_CHECKING:
    from app.config_store import ConfigStore

_DEDUP_WINDOW = 30
_DEFAULT_MAX_ITEMS = 12
_DEFAULT_SPEED_SCALE = 1.5
_MIN_SPEED_SCALE = 0.5
_MAX_SPEED_SCALE = 5.0
_PIXELS_PER_SECOND_BASE = 120.0


@dataclass
class FloatingPanelItem:
    """单条悬浮窗消息的状态（主线程读写）。"""

    content: str
    current_y: float
    height: float
    created_at: float
    opacity: float = 1.0
    batch_id: int = 0
    pixmap: object | None = None


class FloatingPanelEngine:
    """底部进入后以统一速度持续上滚，越顶后删除。"""

    def __init__(self, config: "ConfigStore"):
        self.config = config
        self._items: list[FloatingPanelItem] = []
        self._recent: deque[str] = deque(maxlen=_DEDUP_WINDOW)
        self.running: bool = False
        self._panel_height: float = 600.0
        self._max_items: int = _DEFAULT_MAX_ITEMS
        self._speed_scale: float = _DEFAULT_SPEED_SCALE
        self._pixels_per_second: float = _PIXELS_PER_SECOND_BASE * _DEFAULT_SPEED_SCALE
        self.apply_config()

    def apply_config(self) -> None:
        raw_max = self.config.get("floating_panel_max_items", "")
        try:
            self._max_items = max(1, min(int(raw_max or _DEFAULT_MAX_ITEMS), 50))
        except (TypeError, ValueError):
            self._max_items = _DEFAULT_MAX_ITEMS

        raw_speed = self.config.get("floating_panel_speed", "")
        try:
            self._speed_scale = max(
                _MIN_SPEED_SCALE,
                min(float(raw_speed or _DEFAULT_SPEED_SCALE), _MAX_SPEED_SCALE),
            )
        except (TypeError, ValueError):
            self._speed_scale = _DEFAULT_SPEED_SCALE
        self._pixels_per_second = _PIXELS_PER_SECOND_BASE * self._speed_scale

    def set_panel_height(self, height: float) -> None:
        self._panel_height = max(1.0, float(height))

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def clear(self) -> None:
        self._items.clear()
        self._recent.clear()

    def visible_items(self) -> list[FloatingPanelItem]:
        return list(self._items)

    def visible_count(self) -> int:
        return len(self._items)

    def active_count(self) -> int:
        return self.visible_count()

    @property
    def pixels_per_second(self) -> float:
        return self._pixels_per_second

    def needs_render_tick(self) -> bool:
        return bool(self._items)

    def is_duplicate(self, content: str) -> bool:
        return content in self._recent

    def _remember(self, content: str) -> None:
        self._recent.append(content)

    def _enforce_max_items(self) -> None:
        """仅用于上限兜底；超限时立即丢弃最旧条目。"""
        while len(self._items) > self._max_items:
            self._items.pop(0)

    def add_text(
        self,
        content: str,
        persona: str = "",
        *,
        item_height: float,
        batch_id: int = 0,
        scene_generation: int = 0,
        skip_dedup: bool = False,
        now: float | None = None,
    ) -> FloatingPanelItem | None:
        del persona, scene_generation  # API 对齐 DanmuEngine.add_text
        text = normalize_danmu_display_text(content, self.config)
        if not text:
            return None
        if not skip_dedup and self.is_duplicate(text):
            return None

        ts = 0.0 if now is None else float(now)
        height = max(24.0, float(item_height))
        # 新条目始终从面板底部基线加入，不因已有条目做瞬间重排。
        start_y = self._panel_height
        item = FloatingPanelItem(
            content=text,
            current_y=start_y,
            height=height,
            created_at=ts,
            batch_id=batch_id,
        )
        self._items.append(item)
        self._remember(text)
        self._enforce_max_items()
        return item

    def update_item_height(self, item: FloatingPanelItem, height: float) -> None:
        """Overlay 实测高度后回调；连续上滚语义下不做重排。"""
        item.height = max(24.0, float(height))

    def update(self, dt_sec: float, now: float | None = None) -> bool:
        """推进动画；返回是否仍需渲染 tick。"""
        if not self._items:
            return False
        del now  # 连续上滚模式不再使用 lifetime / fade-out 语义。
        dt = max(0.0, min(float(dt_sec), 0.1))
        move = self._pixels_per_second * dt

        surviving: list[FloatingPanelItem] = []
        for item in self._items:
            item.current_y -= move
            if item.current_y + item.height < 0.0:
                continue
            surviving.append(item)

        self._items = surviving
        self._enforce_max_items()
        return self.needs_render_tick()
