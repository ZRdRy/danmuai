"""读弹幕 TTS 平台/模型/音色目录（Web 联动与 voice 白名单）。

豆包音色按官方 resource 规则推断；百炼 qwen3 音色来自探测与文档。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.tts_providers import (
    TTS_PROVIDER_CUSTOM_OPENAI,
    TTS_PROVIDER_DASHSCOPE_QWEN,
    TTS_PROVIDER_DOUBAO,
    TTS_PROVIDER_MIMO,
)

DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DASHSCOPE_REALTIME_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


@dataclass(frozen=True)
class TtsVoiceSpec:
    id: str
    label_zh: str
    supports_style: bool = False


@dataclass(frozen=True)
class TtsModelSpec:
    id: str
    label_zh: str
    voices: tuple[TtsVoiceSpec, ...]
    supports_style: bool = False
    transport: str = "http"  # http | websocket | chat_audio


@dataclass(frozen=True)
class TtsProviderCatalog:
    id: str
    label_zh: str
    models: tuple[TtsModelSpec, ...]
    needs_app_id: bool = False


def infer_doubao_resource_id(speaker: str) -> str:
    if "_uranus_bigtts" in speaker or speaker.startswith("saturn_"):
        return "seed-tts-2.0"
    return "seed-tts-1.0"


DOUBAO_VOICES: tuple[TtsVoiceSpec, ...] = (
    TtsVoiceSpec("zh_female_vv_uranus_bigtts", "Vivi 2.0", supports_style=True),
    TtsVoiceSpec("zh_male_ruyayichen_uranus_bigtts", "儒雅逸辰 2.0", supports_style=True),
    TtsVoiceSpec("zh_female_tianmeixiaoyuan_uranus_bigtts", "甜美小源 2.0", supports_style=True),
    TtsVoiceSpec("zh_male_m191_uranus_bigtts", "云舟", supports_style=True),
    TtsVoiceSpec("zh_female_cancan_mars_bigtts", "灿灿 / Shiny"),
    TtsVoiceSpec("zh_male_qingshuangnanda_mars_bigtts", "清爽男大"),
    TtsVoiceSpec("zh_female_linjianvhai_moon_bigtts", "邻家女孩"),
    TtsVoiceSpec("zh_male_yuanboxiaoshu_moon_bigtts", "渊博小叔"),
    TtsVoiceSpec("ICL_zh_male_badaozongcai_v1_tob", "霸道总裁"),
    TtsVoiceSpec("ICL_zh_female_wenrounvshen_239eff5e8ffa_tob", "温柔女神"),
)

DASHSCOPE_VOICES: tuple[TtsVoiceSpec, ...] = (
    TtsVoiceSpec("Cherry", "芊悦"),
    TtsVoiceSpec("Serena", "苏瑶"),
    TtsVoiceSpec("Ethan", "晨煦"),
    TtsVoiceSpec("Chelsie", "千雪"),
    TtsVoiceSpec("Momo", "茉兔"),
    TtsVoiceSpec("Vivian", "十三"),
    TtsVoiceSpec("Kai", "凯"),
    TtsVoiceSpec("Bella", "萌宝"),
    TtsVoiceSpec("longanyang", "龙安洋"),
    TtsVoiceSpec("longanhuan_v3", "龙安欢 V3"),
)

MIMO_VOICES: tuple[TtsVoiceSpec, ...] = (
    TtsVoiceSpec("mimo_default", "MiMo-默认"),
    TtsVoiceSpec("冰糖", "冰糖"),
    TtsVoiceSpec("茉莉", "茉莉"),
    TtsVoiceSpec("苏打", "苏打"),
    TtsVoiceSpec("白桦", "白桦"),
    TtsVoiceSpec("Mia", "Mia"),
    TtsVoiceSpec("Chloe", "Chloe"),
    TtsVoiceSpec("Milo", "Milo"),
    TtsVoiceSpec("Dean", "Dean"),
)

TTS_CATALOG: tuple[TtsProviderCatalog, ...] = (
    TtsProviderCatalog(
        id=TTS_PROVIDER_MIMO,
        label_zh="小米 MiMo（默认）",
        models=(
            TtsModelSpec(
                id="mimo-v2.5-tts",
                label_zh="mimo-v2.5-tts",
                voices=MIMO_VOICES,
                transport="chat_audio",
            ),
        ),
    ),
    TtsProviderCatalog(
        id=TTS_PROVIDER_DOUBAO,
        label_zh="火山豆包语音",
        needs_app_id=True,
        models=(
            TtsModelSpec(
                id="seed-tts-2.0",
                label_zh="豆包语音合成 2.0",
                voices=tuple(v for v in DOUBAO_VOICES if infer_doubao_resource_id(v.id) == "seed-tts-2.0"),
                supports_style=True,
                transport="http",
            ),
            TtsModelSpec(
                id="seed-tts-1.0",
                label_zh="豆包语音合成 1.0",
                voices=tuple(v for v in DOUBAO_VOICES if infer_doubao_resource_id(v.id) == "seed-tts-1.0"),
                transport="http",
            ),
            TtsModelSpec(
                id="seed-tts-1.1",
                label_zh="豆包语音合成 1.1",
                voices=DOUBAO_VOICES,
                transport="http",
            ),
        ),
    ),
    TtsProviderCatalog(
        id=TTS_PROVIDER_DASHSCOPE_QWEN,
        label_zh="阿里百炼 Qwen3",
        models=(
            TtsModelSpec(
                id="qwen3-tts-flash-2025-11-27",
                label_zh="Qwen3-TTS Flash",
                voices=DASHSCOPE_VOICES,
                transport="http",
            ),
            TtsModelSpec(
                id="qwen3-tts-flash-realtime",
                label_zh="Qwen3-TTS Flash Realtime",
                voices=DASHSCOPE_VOICES,
                transport="websocket",
            ),
            TtsModelSpec(
                id="qwen3-tts-instruct-flash-realtime",
                label_zh="Qwen3-TTS Instruct Realtime",
                voices=DASHSCOPE_VOICES,
                supports_style=True,
                transport="websocket",
            ),
        ),
    ),
    TtsProviderCatalog(
        id=TTS_PROVIDER_CUSTOM_OPENAI,
        label_zh="自定义（OpenAI 兼容）",
        models=(
            TtsModelSpec(
                id="",
                label_zh="自定义模型",
                voices=(TtsVoiceSpec("", "（在下方手动填写音色）"),),
                transport="chat_audio",
            ),
        ),
    ),
)

_CATALOG_BY_ID = {p.id: p for p in TTS_CATALOG}


def get_tts_catalog_provider(provider_id: str) -> TtsProviderCatalog | None:
    return _CATALOG_BY_ID.get((provider_id or "").strip())


def list_catalog_for_api() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for provider in TTS_CATALOG:
        models: list[dict[str, Any]] = []
        for model in provider.models:
            models.append(
                {
                    "id": model.id,
                    "label": model.label_zh,
                    "supports_style": model.supports_style,
                    "transport": model.transport,
                    "voices": [
                        {"id": v.id, "label": v.label_zh, "supports_style": v.supports_style}
                        for v in model.voices
                    ],
                }
            )
        out.append(
            {
                "id": provider.id,
                "label": provider.label_zh,
                "needs_app_id": provider.needs_app_id,
                "models": models,
            }
        )
    return out


def default_model_for_provider(provider_id: str) -> str:
    cat = get_tts_catalog_provider(provider_id)
    if not cat or not cat.models:
        return ""
    return cat.models[0].id


def default_voice_for_provider(provider_id: str, model_id: str | None = None) -> str:
    cat = get_tts_catalog_provider(provider_id)
    if not cat:
        return "冰糖"
    mid = (model_id or "").strip()
    for model in cat.models:
        if mid and model.id != mid:
            continue
        if model.voices:
            return model.voices[0].id
    if cat.models and cat.models[0].voices:
        return cat.models[0].voices[0].id
    return ""


def voice_ids_for(provider_id: str, model_id: str) -> frozenset[str]:
    cat = get_tts_catalog_provider(provider_id)
    if not cat:
        return frozenset()
    mid = (model_id or "").strip()
    for model in cat.models:
        if model.id == mid or (not mid and model.id):
            return frozenset(v.id for v in model.voices if v.id)
    return frozenset()


def model_supports_style(provider_id: str, model_id: str) -> bool:
    cat = get_tts_catalog_provider(provider_id)
    if not cat:
        return False
    for model in cat.models:
        if model.id == model_id:
            return model.supports_style
    return False


def normalize_catalog_voice(
    voice: str | None,
    *,
    provider_id: str,
    model_id: str,
) -> str:
    raw = (voice or "").strip()
    allowed = voice_ids_for(provider_id, model_id)
    if raw in allowed:
        return raw
    default = default_voice_for_provider(provider_id, model_id)
    return default if default else raw
