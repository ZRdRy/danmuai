from unittest.mock import patch

from app.translations import Translator


def test_resolve_language_prefers_saved_value():
    assert Translator.resolve_language("zh") == "zh"
    assert Translator.resolve_language("en") == "en"


def test_resolve_language_falls_back_to_system_locale():
    with patch.object(Translator, "detect_system_language", return_value="en"):
        assert Translator.resolve_language("") == "en"
        assert Translator.resolve_language("fr") == "en"


def test_detect_system_language_maps_chinese_locale():
    with patch("app.translations.QLocale.system") as mock_system:
        mock_system.return_value.name.return_value = "zh_CN"
        assert Translator.detect_system_language() == "zh"


def test_detect_system_language_maps_non_chinese_to_english():
    with patch("app.translations.QLocale.system") as mock_system:
        mock_system.return_value.name.return_value = "en_US"
        assert Translator.detect_system_language() == "en"
