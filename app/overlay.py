from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (QPainter, QColor, QPen, QFont, QFontMetrics,
                         QPixmap, QPainterPath)

import sys
import ctypes

from app.config_store import ConfigStore
from app.danmu_engine import DanmuEngine

if sys.platform == "win32":
    _GWL_EXSTYLE = -20
    _WS_EX_LAYERED = 0x00080000
    _WS_EX_TRANSPARENT = 0x00000020
    try:
        _SetWindowLong = ctypes.windll.user32.SetWindowLongPtrW
        _GetWindowLong = ctypes.windll.user32.GetWindowLongPtrW
    except AttributeError:
        _SetWindowLong = ctypes.windll.user32.SetWindowLongW
        _GetWindowLong = ctypes.windll.user32.GetWindowLongW


class DanmuOverlay(QWidget):
    def __init__(self, config: ConfigStore, engine: DanmuEngine):
        super().__init__()
        self.config = config
        self.engine = engine

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setStyleSheet("background: transparent;")

        self.font = QFont("Microsoft YaHei", 22)
        self.font.setBold(True)
        self.font_metrics = QFontMetrics(self.font)

        self._screen_width: float = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _apply_win32_click_through(self):
        if sys.platform != "win32":
            return
        hwnd = int(self.winId())
        ex_style = _GetWindowLong(hwnd, _GWL_EXSTYLE)
        _SetWindowLong(hwnd, _GWL_EXSTYLE,
                       ex_style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT)

    def _tick(self):
        self.engine.update()
        self.update()

    def measure_item_width(self, item):
        item.width = float(self.font_metrics.horizontalAdvance(item.content))

    def _render_item_pixmap(self, item) -> QPixmap:
        w = int(item.width) + 10
        h = self.font_metrics.height() + 10
        dpr = self.devicePixelRatio()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        p = QPainter(pm)
        p.setFont(self.font)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        baseline_y = self.font_metrics.ascent() + 5
        text_x = 5

        path = QPainterPath()
        path.addText(text_x, baseline_y, self.font, item.content)

        outline_pen = QPen(QColor(0, 0, 0, 200))
        outline_pen.setWidth(4)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(outline_pen)
        p.drawPath(path)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(item.color)
        p.drawPath(path)
        p.end()
        return pm

    def _item_opacity(self, item) -> float:
        screen_width = self._screen_width or float(self.width())
        if screen_width <= 0:
            return 1.0

        fade_in = 120.0
        fade_out = 90.0

        enter_alpha = 1.0
        if item.x > screen_width - fade_in:
            enter_alpha = max(0.0, min(1.0, (screen_width - item.x) / fade_in))

        exit_alpha = 1.0
        right_edge = item.x + item.width
        if right_edge < fade_out:
            exit_alpha = max(0.0, min(1.0, right_edge / fade_out))

        return min(enter_alpha, exit_alpha)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        for track in self.engine.tracks:
            for item in track.items:
                if item.width <= 0:
                    item.width = float(self.font_metrics.horizontalAdvance(item.content))

                if item._pixmap is None:
                    item._pixmap = self._render_item_pixmap(item)

                x = item.x
                y = item.y + 30

                opacity = self._item_opacity(item)
                if opacity <= 0.0:
                    continue

                painter.save()
                painter.setOpacity(opacity)
                painter.drawPixmap(QPointF(x, y), item._pixmap)
                painter.restore()

    def show_for_screen(self, screen_index: int = 0):
        screens = QApplication.screens()
        if screen_index < len(screens):
            geo = screens[screen_index].geometry()
            self.setGeometry(geo)
            self._screen_width = float(geo.width())
            self.engine.set_screen_width(self._screen_width)
            self.engine.set_screen_height(float(geo.height()))
            self.engine.reload_tracks()
        self.show()
        self._apply_win32_click_through()
