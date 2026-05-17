from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QCursor, QPixmap


class ScreenCapturer:
    def __init__(self, config=None):
        self.config = config

    def grab(self) -> QPixmap | None:
        screens = QApplication.screens()
        if not screens:
            return None
        
        target_screen = screens[0]
        geo = target_screen.geometry()
        return target_screen.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
