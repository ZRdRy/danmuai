from app.tts_catalog import (
    default_voice_for_provider,
    infer_doubao_resource_id,
    list_catalog_for_api,
    normalize_catalog_voice,
    voice_ids_for,
)
from app.tts_providers import TTS_PROVIDER_DASHSCOPE_QWEN, TTS_PROVIDER_DOUBAO, TTS_PROVIDER_MIMO


def test_infer_doubao_resource_id():
    assert infer_doubao_resource_id("zh_female_vv_uranus_bigtts") == "seed-tts-2.0"
    assert infer_doubao_resource_id("zh_female_cancan_mars_bigtts") == "seed-tts-1.0"


def test_list_catalog_for_api_has_providers():
    data = list_catalog_for_api()
    ids = {p["id"] for p in data}
    assert TTS_PROVIDER_MIMO in ids
    assert TTS_PROVIDER_DOUBAO in ids
    assert TTS_PROVIDER_DASHSCOPE_QWEN in ids


def test_normalize_catalog_voice_dashscope():
    voice = normalize_catalog_voice(
        "invalid",
        provider_id=TTS_PROVIDER_DASHSCOPE_QWEN,
        model_id="qwen3-tts-flash-2025-11-27",
    )
    assert voice == "Cherry"


def test_voice_ids_for_doubao_2_0():
    allowed = voice_ids_for(TTS_PROVIDER_DOUBAO, "seed-tts-2.0")
    assert "zh_female_vv_uranus_bigtts" in allowed
    assert "zh_female_cancan_mars_bigtts" not in allowed


def test_default_voice_mimo():
    assert default_voice_for_provider(TTS_PROVIDER_MIMO) == "mimo_default"
