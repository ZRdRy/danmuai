import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

from app.logger import SanitizedLogger


class _ToggleBridge(QObject):
    toggle = pyqtSignal()


class HotkeyManager(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._hotkey_str = "ctrl+shift+b"
        self._registered = False
        self._registered_hotkey_str = ""
        self._bridge = _ToggleBridge()
        self._bridge.toggle.connect(self.app.toggle)

    def register(self, keys: str = ""):
        self.unregister()
        if keys:
            self._hotkey_str = keys.lower().replace("ctrl+shift+", "ctrl+shift+")
        try:
            keyboard.add_hotkey(self._hotkey_str, self._bridge.toggle.emit)
            self._registered = True
            self._registered_hotkey_str = self._hotkey_str
        except Exception as e:
            import traceback
            logger = SanitizedLogger()
            logger.warning(f"[Hotkey] registration failed: {e}\n{traceback.format_exc()}")

    def unregister(self):
        if self._registered and self._registered_hotkey_str:
            try:
                keyboard.remove_hotkey(self._registered_hotkey_str)
            except Exception:
                pass
        self._registered = False
        self._registered_hotkey_str = ""

    def set_keys(self, keys: str):
        hotkey = keys.lower().replace(" ", "")
        if hotkey == self._hotkey_str:
            return
        self._hotkey_str = hotkey
        if self._registered:
            self.register()

    @property
    def hotkey_str(self) -> str:
        return self._hotkey_str
