from PyQt6.QtCore import QLocale, QObject, pyqtSignal

from app.translations_danmu import TRANSLATIONS_EN as DANMU_EN
from app.translations_danmu import TRANSLATIONS_ZH as DANMU_ZH
from app.translations_settings import TRANSLATIONS_EN as SETTINGS_EN
from app.translations_settings import TRANSLATIONS_ZH as SETTINGS_ZH
from app.translations_ui import TRANSLATIONS_EN as UI_EN
from app.translations_ui import TRANSLATIONS_ZH as UI_ZH

TRANSLATIONS = {
    "zh": {**UI_ZH, **DANMU_ZH, **SETTINGS_ZH},
    "en": {**UI_EN, **DANMU_EN, **SETTINGS_EN},
}


class Translator(QObject):
    language_changed = pyqtSignal()
    _instance = None
    _lang = "zh"

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def detect_system_language(cls) -> str:
        locale_name = QLocale.system().name().lower()
        if locale_name.startswith("zh"):
            return "zh"
        return "en"

    @classmethod
    def resolve_language(cls, configured_lang: str = "") -> str:
        if configured_lang in TRANSLATIONS:
            return configured_lang
        return cls.detect_system_language()

    @classmethod
    def set_language(cls, lang: str):
        if lang not in TRANSLATIONS:
            lang = "zh"
        if cls._lang != lang:
            cls._lang = lang
            if cls._instance:
                cls._instance.language_changed.emit()

    @classmethod
    def get_language(cls) -> str:
        return cls._lang

    @classmethod
    def tr(cls, key: str, default: str = "") -> str:
        lang_dict = TRANSLATIONS.get(cls._lang, {})
        return lang_dict.get(key, default or key)


def tr(key: str, default: str = "") -> str:
    return Translator.tr(key, default)
