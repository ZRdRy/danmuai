"""Deprecated 兼容壳：W-FP-V2-001 起请使用 FloatingPanelEngine + FloatingPanelOverlay。

保留本模块仅为旧 import / 测试过渡；运行时主路径由 main_lifecycle_mixin 直接持有 V2 对象。
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from app.floating_panel_engine import FloatingPanelEngine, FloatingPanelItem
from app.floating_panel_overlay import FloatingPanelOverlay

if TYPE_CHECKING:
    from app.config_store import ConfigStore

_DEPRECATION_MSG = (
    "app.floating_panel.FloatingPanel is deprecated; "
    "use FloatingPanelEngine + FloatingPanelOverlay (W-FP-V2-001)"
)


def _warn_deprecated() -> None:
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=3)


class FloatingPanel:
    """Deprecated wrapper：委托 V2 engine + overlay，API 与 W-FP-002 对齐。"""

    def __init__(self, config: "ConfigStore"):
        _warn_deprecated()
        self.config = config
        self._engine = FloatingPanelEngine(config)
        self._overlay = FloatingPanelOverlay(config, self._engine)

    @property
    def _active_items(self):
        return self._engine.visible_items()

    def feed(self, content: str, persona: str = "") -> None:
        self._overlay.add_danmu_text(content, persona or "")

    def set_display_mode(self, mode: str) -> None:
        normalized = (mode or "overlay").strip().lower()
        if normalized in ("floating_panel", "both"):
            self._engine.start()
            from app.snipper import resolve_screen_index

            self._overlay.show_for_screen(resolve_screen_index(self.config))
        else:
            self._overlay.reset_session_state()

    def apply_config(self) -> None:
        self._overlay.apply_config()

    def is_render_active(self) -> bool:
        return self._overlay.is_render_active()

    def active_count(self) -> int:
        return self._overlay.active_count()

    def reset_session_state(self) -> None:
        self._overlay.reset_session_state()


__all__ = ["FloatingPanel", "FloatingPanelEngine", "FloatingPanelItem", "FloatingPanelOverlay"]
