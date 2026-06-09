"""读弹幕 TTS 平台/模型/音色目录（Web 联动与 voice 白名单）。

百炼 qwen3 音色来自探测与文档。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.tts_providers import (
    TTS_PROVIDER_DASHSCOPE_QWEN,
    TTS_PROVIDER_MIMO,
)

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
