"""W-TEST-COVER-013: runtime language switch updates tr() output."""

from app.translations import Translator, tr


def test_set_language_switches_known_keys():
    Translator.set_language("zh")
    zh = tr("config.error_api_endpoint_required")
    Translator.set_language("en")
    en = tr("config.error_api_endpoint_required")
    assert zh != en
    assert zh
    assert en
    Translator.set_language("zh")
