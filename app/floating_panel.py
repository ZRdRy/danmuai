"""弹幕姬式悬浮窗：独立 QWidget，置顶 + 拖动 + 缩放 + 透明度/字体/最大条数/速度/鼠标穿透可配。

W-FP-002 实现本体；W-FP-001 提供 6 个配置键，W-FP-003 负责 `_consume_reply_queue` 旁路分发与 Web 开关。

设计原则：
1. 事件驱动渲染 — 队列为空时 QTimer 已停止，CPU 占用接近 0；新弹幕入队时 `_kick_render()` 启动 timer；
2. 动画期间 16ms tick 推进位置 + 重绘；所有可见条目滚出顶部后自动停表；
3. 不挂 DanmuEngine — 悬浮窗独立去重窗口（`deque(30)`）、独立位置/大小，独立字体/速度；
4. 不复用 DanmuOverlay._tick — 与横向 overlay 互不干扰；
5. 位置/大小仅在内存中维护；持久化由 W-FP-003 通过 `apply_config()` 触发。
"""
from __future__ import annotations

import ctypes
import logging
import sys
from collections import deque
from typing import TYPE_CHECKING

from PyQt6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QSizeGrip, QWidget

from app.danmu_engine import normalize_danmu_display_text

if TYPE_CHECKING:
    from app.config_store import ConfigStore

if sys.platform == "win32":
    _GWL_EXSTYLE = -20
    _WS_EX_LAYERED = 0x00080000
    _WS_EX_TRANSPARENT = 0x00000020
    _HWND_TOPMOST = -1
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOACTIVATE = 0x0010
    _SWP_SHOWWINDOW = 0x0040
    try:
        _SetWindowLong = ctypes.windll.user32.SetWindowLongPtrW
        _GetWindowLong = ctypes.windll.user32.GetWindowLongPtrW
    except AttributeError:
        _SetWindowLong = ctypes.windll.user32.SetWindowLongW
        _GetWindowLong = ctypes.windll.user32.GetWindowLongW
    _SetWindowPos = ctypes.windll.user32.SetWindowPos

_FRAME_DT = 1.0 / 60.0
_TICK_INTERVAL_MS = 16
_DT_CAP_SEC = 0.1
_FADE_IN_PX = 30.0
_FADE_OUT_PX = 30.0
_DEFAULT_WIDTH = 400
_DEFAULT_HEIGHT = 600
_MIN_PANEL_WIDTH = 120
_MIN_PANEL_HEIGHT = 160
_DEDUP_WINDOW = 30

# 文本颜色：白色填充 + 黑色描边（与 DanmuOverlay._render_item_pixmap 风格一致）
_TEXT_FILL = QColor(255, 255, 255)
_TEXT_OUTLINE = QColor(0, 0, 0, 200)
_OUTLINE_WIDTH = 4

logger = logging.getLogger("danmu.floating_panel")


class _FloatingItem:
    """单条弹幕条目：仅在主线程内被读写。"""

    __slots__ = ("content", "y", "height", "pixmap", "dpr")

    def __init__(self, content: str, y: float, height: float, pixmap: QPixmap, dpr: float):
        self.content = content
        self.y = y
        self.height = height
        self.pixmap = pixmap
        self.dpr = dpr

    def bottom(self) -> float:
        return self.y + self.height


class FloatingPanel(QWidget):
    """弹幕姬式悬浮窗。

    - 6 项配置由 W-FP-001 落库，由 W-FP-003 的 `DanmuApp._on_config_changed` 触发 `apply_config`；
    - 默认隐藏；`set_display_mode` 接受 `overlay` / `floating_panel` / `both`；
    - 事件驱动渲染：无内容时 `timer.isActive() == False`。
    """

    def __init__(self, config: "ConfigStore"):
        super().__init__()
        self.config = config
        self._active_items: list[_FloatingItem] = []
        self._recent: deque[str] = deque(maxlen=_DEDUP_WINDOW)
        self._display_mode: str = "overlay"

        self._font_size: int = 18
        self._opacity_pct: int = 85
        self._max_items: int = 60
        self._speed: float = 1.5
        self._click_through: bool = True

        self._font: QFont | None = None
        self._font_metrics: QFontMetrics | None = None

        self._timer_interval_ms: int = _TICK_INTERVAL_MS
        self._tick_clock = QElapsedTimer()
        self._last_tick_valid: bool = False
        self.last_tick_dt_sec: float = _FRAME_DT

        # 拖动状态
        self._drag_position: QPoint | None = None
        self._geometry_initialized: bool = False

        self.setMinimumSize(_MIN_PANEL_WIDTH, _MIN_PANEL_HEIGHT)

        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent;")

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)

        # 右下角缩放手柄
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(16, 16)

        self._apply_config()

    # ---------- public API ----------

    def feed(self, content: str, persona: str = "") -> None:
        """从 `_consume_reply_queue` 旁路接收一条已上屏弹幕。

        - 应用与 Overlay 相同的截断规则（`normalize_danmu_display_text`）；
        - 内部 `deque(30)` 去重窗口避免滚出顶部前的纯重复；
        - 入队后 `_kick_render()` 启动/保持 timer。
        """
        if not content:
            return
        if self._display_mode == "overlay":
            return
        if self._font is None or self._font_metrics is None:
            return

        text = normalize_danmu_display_text(content, self.config)
        if not text:
            return
        if self._is_duplicate(text):
            return

        dpr = self.devicePixelRatio() or 1.0
        width = self._font_metrics.horizontalAdvance(text) + 10
        height = self._font_metrics.height() + 10
        pixmap = self._render_item_pixmap(text, width, height, dpr)

        # 起点：从窗口底部外侧稍下方进入，淡入更自然
        start_y = float(self.height()) + 4.0
        item = _FloatingItem(content=text, y=start_y, height=height, pixmap=pixmap, dpr=dpr)
        self._active_items.append(item)
        self._remember(text)

        if len(self._active_items) > self._max_items:
            overflow = len(self._active_items) - self._max_items
            del self._active_items[:overflow]

        self._kick_render()

    def set_display_mode(self, mode: str) -> None:
        """根据 `display_mode` 决定显示或隐藏。"""
        normalized = (mode or "overlay").strip().lower()
        if normalized not in ("overlay", "floating_panel", "both"):
            normalized = "overlay"
        self._display_mode = normalized
        if normalized in ("floating_panel", "both"):
            self._ensure_geometry()
            self.show()
            self._apply_win32_click_through()
            if self._active_items:
                self._kick_render()
        else:
            self._stop_render()
            self.hide()

    def apply_config(self) -> None:
        """热更新 6 项配置（主线程；W-FP-003 在 `_on_config_changed` 中调用）。"""
        previous_max = self._max_items
        previous_click_through = self._click_through
        self._apply_config()
        if self._max_items < previous_max and len(self._active_items) > self._max_items:
            del self._active_items[: len(self._active_items) - self._max_items]
        if self._click_through != previous_click_through:
            self._apply_win32_click_through()
        if self.isVisible():
            self.update()

    def is_render_active(self) -> bool:
        """便于测试断言事件驱动：返回 QTimer 是否 active。"""
        return self.timer.isActive()

    def active_count(self) -> int:
        return len(self._active_items)

    # ---------- internals ----------

    def _apply_config(self) -> None:
        def _safe_int(key: str, default: int) -> int:
            raw = self.config.get(key, "")
            if raw == "":
                return default
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default

        def _safe_float(key: str, default: float) -> float:
            raw = self.config.get(key, "")
            if raw == "":
                return default
            try:
                return float(raw)
            except (TypeError, ValueError):
                return default

        self._font_size = max(12, min(48, _safe_int("floating_panel_font_size", 18)))
        self._opacity_pct = max(0, min(100, _safe_int("floating_panel_opacity", 85)))
        self._max_items = max(5, min(200, _safe_int("floating_panel_max_items", 60)))
        self._speed = max(0.5, min(5.0, _safe_float("floating_panel_speed", 1.5)))
        self._click_through = (
            str(self.config.get("floating_panel_click_through", "1") or "1").strip().lower()
            not in ("0", "false", "no")
        )
        self._font = QFont("Microsoft YaHei", self._font_size)
        self._font.setBold(True)
        self._font_metrics = QFontMetrics(self._font)

    def _is_duplicate(self, content: str) -> bool:
        if content in self._recent:
            return True
        for prev in self._recent:
            if content == prev:
                return True
        return False

    def _remember(self, content: str) -> None:
        self._recent.append(content)

    def _kick_render(self) -> None:
        if not self.isVisible():
            return
        if not self.timer.isActive():
            self._last_tick_valid = False
            self.timer.start(self._timer_interval_ms)
            self._tick()

    def _stop_render(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
        self._last_tick_valid = False

    def _tick_dt_sec(self) -> float:
        if not self._last_tick_valid:
            self._tick_clock.start()
            self._last_tick_valid = True
            return _FRAME_DT
        dt = self._tick_clock.restart() / 1000.0
        if dt <= 0.0:
            return _FRAME_DT
        return min(dt, _DT_CAP_SEC)

    def _tick(self) -> None:
        if not self.isVisible():
            self._stop_render()
            return

        dt = self._tick_dt_sec()
        self.last_tick_dt_sec = dt

        # 向上滚动
        for item in self._active_items:
            item.y -= self._speed * dt * 60.0  # 与 DanmuEngine speed 语义对齐

        # 移除已滚出顶部的条目
        kept: list[_FloatingItem] = []
        for item in self._active_items:
            if item.y + item.height < 0:
                continue
            kept.append(item)
        self._active_items = kept

        self.update()

        if not self._active_items:
            self._stop_render()

    def _render_item_pixmap(self, text: str, width: int, height: int, dpr: float) -> QPixmap:
        w_px = max(1, int(width * dpr))
        h_px = max(1, int(height * dpr))
        pm = QPixmap(w_px, h_px)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setFont(self._font)
            baseline_y = self._font_metrics.ascent() + 5
            text_x = 5
            path = QPainterPath()
            path.addText(text_x, baseline_y, self._font, text)
            pen = QPen(_TEXT_OUTLINE)
            pen.setWidth(_OUTLINE_WIDTH)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_TEXT_FILL)
            painter.drawPath(path)
        finally:
            painter.end()
        return pm

    def _item_opacity(self, item: _FloatingItem) -> float:
        """顶部 30px 渐隐，底部 30px 渐入。"""
        h = float(self.height())
        if h <= 0:
            return 1.0
        bottom = item.y + item.height
        # 顶渐隐
        exit_alpha = 1.0
        if bottom < _FADE_OUT_PX:
            exit_alpha = max(0.0, min(1.0, bottom / _FADE_OUT_PX))
        # 底渐入
        enter_alpha = 1.0
        if item.y > h - _FADE_IN_PX:
            enter_alpha = max(0.0, min(1.0, (h - item.y) / _FADE_IN_PX))
        return min(enter_alpha, exit_alpha)

    def paintEvent(self, event) -> None:
        if not self._active_items or self._font_metrics is None:
            return
        global_alpha = max(0.0, min(1.0, self._opacity_pct / 100.0))
        if global_alpha <= 0.0:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            for item in self._active_items:
                alpha = self._item_opacity(item) * global_alpha
                if alpha <= 0.0:
                    continue
                painter.setOpacity(alpha)
                painter.drawPixmap(QPoint(0, int(item.y)), item.pixmap)
            painter.setOpacity(1.0)
        finally:
            painter.end()

    def resizeEvent(self, event) -> None:
        # QSizeGrip 默认在右下角，宽度为 16
        if self._grip is not None:
            self._grip.move(self.width() - 16, self.height() - 16)
        super().resizeEvent(event)

    # ---------- 拖动 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._click_through:
            self._drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self._drag_position = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------- Win32 透明置顶 ----------

    def _apply_win32_click_through(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        if not hwnd:
            return
        ex_style = _GetWindowLong(hwnd, _GWL_EXSTYLE)
        new_style = ex_style | _WS_EX_LAYERED
        if self._click_through:
            new_style |= _WS_EX_TRANSPARENT
        else:
            new_style &= ~_WS_EX_TRANSPARENT
        _SetWindowLong(hwnd, _GWL_EXSTYLE, new_style)

    def reassert_topmost(self) -> None:
        """对外可调：被其它置顶窗抢栈后恢复 HWND_TOPMOST。"""
        if not self.isVisible():
            return
        self.raise_()
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        if not hwnd:
            return
        _SetWindowPos(
            hwnd,
            _HWND_TOPMOST,
            0,
            0,
            0,
            0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW,
        )

    # ---------- 几何 ----------

    def _apply_default_geometry(self) -> None:
        """首次显示时落位到主屏右下角 400×600（勿用 width()>0 判断，未 show 前 Qt 默认 640×480 会误跳过）。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.setGeometry(100, 100, _DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        else:
            avail = screen.availableGeometry()
            w = min(_DEFAULT_WIDTH, avail.width())
            h = min(_DEFAULT_HEIGHT, avail.height())
            x = avail.x() + avail.width() - w - 40
            y = avail.y() + avail.height() - h - 80
            self.setGeometry(x, y, w, h)
        self._geometry_initialized = True

    def _ensure_geometry(self) -> None:
        if self._geometry_initialized:
            return
        self._apply_default_geometry()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Tool 窗首次 show 可能被 Qt 缩到 QSizeGrip 尺寸；低于阈值则强制恢复默认几何
        if self.width() < _MIN_PANEL_WIDTH or self.height() < _MIN_PANEL_HEIGHT:
            self._apply_default_geometry()
        self._apply_win32_click_through()
        self.reassert_topmost()
        if self._active_items:
            self._kick_render()

    def hideEvent(self, event) -> None:
        self._stop_render()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._stop_render()
        super().closeEvent(event)


__all__ = ["FloatingPanel"]
