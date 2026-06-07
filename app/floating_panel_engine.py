"""侧边悬浮窗弹幕引擎：底入堆叠、停留 lifetime 后淡出；不依赖 DanmuEngine 轨道逻辑。

W-FP-V2-001：纯状态机，由 FloatingPanelOverlay 驱动 update 与绘制。
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.danmu_engine import normalize_danmu_display_text

if TYPE_CHECKING:
    from app.config_store import ConfigStore

_ITEM_GAP = 8.0
_MOVE_SPEED_PX = 520.0
_FADE_IN_SEC = 0.25
_FADE_OUT_SEC = 0.45
_DEDUP_WINDOW = 30
_DEFAULT_MAX_ITEMS = 12
_DEFAULT_LIFETIME_SEC = 7.0


@dataclass
class FloatingPanelItem:
    """单条悬浮窗消息的状态（主线程读写）。"""

    content: str
    target_y: float
    current_y: float
    height: float
    created_at: float
    fade_state: str = "enter"
    opacity: float = 0.0
    batch_id: int = 0
    pixmap: object | None = None


class FloatingPanelEngine:
    """底入 → 堆叠上移 → lifetime 到期淡出删除。"""

    def __init__(self, config: "ConfigStore"):
        self.config = config
        self._items: list[FloatingPanelItem] = []
        self._recent: deque[str] = deque(maxlen=_DEDUP_WINDOW)
        self.running: bool = False
        self._panel_height: float = 600.0
        self._max_items: int = _DEFAULT_MAX_ITEMS
        self._lifetime_sec: float = _DEFAULT_LIFETIME_SEC
        self.apply_config()

    def apply_config(self) -> None:
        raw_max = self.config.get("floating_panel_max_items", "")
        try:
            self._max_items = max(1, min(int(raw_max or _DEFAULT_MAX_ITEMS), 50))
        except (TypeError, ValueError):
            self._max_items = _DEFAULT_MAX_ITEMS
        raw_life = self.config.get("floating_panel_lifetime_sec", "")
        try:
            self._lifetime_sec = max(2.0, min(float(raw_life or _DEFAULT_LIFETIME_SEC), 60.0))
        except (TypeError, ValueError):
            self._lifetime_sec = _DEFAULT_LIFETIME_SEC

    def set_panel_height(self, height: float) -> None:
        self._panel_height = max(1.0, float(height))
        self._relayout_targets()

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

    def needs_render_tick(self) -> bool:
        if not self._items:
            return False
        now = time.monotonic()
        for item in self._items:
            if item.fade_state != "hold":
                return True
            if abs(item.current_y - item.target_y) > 0.5:
                return True
            if now >= item.created_at + self._lifetime_sec:
                return True
        return False

    def is_duplicate(self, content: str) -> bool:
        return content in self._recent

    def _remember(self, content: str) -> None:
        self._recent.append(content)

    def _relayout_targets(self) -> None:
        """自下而上重算堆叠 target_y。"""
        y = self._panel_height
        for item in reversed(self._items):
            y -= item.height + _ITEM_GAP
            item.target_y = max(0.0, y)

    def _enforce_max_items(self, now: float) -> None:
        while len(self._items) > self._max_items:
            oldest = self._items[0]
            if oldest.fade_state != "exit":
                oldest.fade_state = "exit"
            if oldest.opacity <= 0.0:
                self._items.pop(0)
            else:
                break

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

        ts = now if now is not None else time.monotonic()
        height = max(24.0, float(item_height))
        start_y = self._panel_height
        item = FloatingPanelItem(
            content=text,
            target_y=start_y,
            current_y=start_y,
            height=height,
            created_at=ts,
            fade_state="enter",
            opacity=0.0,
            batch_id=batch_id,
        )
        self._items.append(item)
        self._remember(text)
        self._relayout_targets()
        self._enforce_max_items(ts)
        return item

    def update_item_height(self, item: FloatingPanelItem, height: float) -> None:
        """Overlay 实测高度后回调，重算堆叠。"""
        item.height = max(24.0, float(height))
        self._relayout_targets()

    def update(self, dt_sec: float, now: float | None = None) -> bool:
        """推进动画；返回是否仍需渲染 tick。"""
        if not self._items:
            return False
        ts = now if now is not None else time.monotonic()
        dt = max(0.0, min(float(dt_sec), 0.1))
        move = _MOVE_SPEED_PX * dt

        surviving: list[FloatingPanelItem] = []
        for item in self._items:
            if item.fade_state == "exit":
                item.opacity = max(0.0, item.opacity - dt / _FADE_OUT_SEC)
            elif ts >= item.created_at + self._lifetime_sec:
                item.fade_state = "exit"
                item.opacity = max(0.0, item.opacity - dt / _FADE_OUT_SEC)
            elif item.fade_state == "enter":
                item.opacity = min(1.0, item.opacity + dt / _FADE_IN_SEC)
                if item.opacity >= 1.0:
                    item.fade_state = "hold"
            else:
                item.opacity = 1.0

            if item.current_y > item.target_y:
                item.current_y = max(item.target_y, item.current_y - move)
            elif item.current_y < item.target_y:
                item.current_y = min(item.target_y, item.current_y + move)

            if item.fade_state == "exit" and item.opacity <= 0.0:
                continue
            surviving.append(item)

        self._items = surviving
        self._enforce_max_items(ts)
        return self.needs_render_tick()
