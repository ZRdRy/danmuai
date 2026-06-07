"""MiMo V2.5 TTS 非流式合成（向后兼容门面，实现见 tts_providers）。

读弹幕 TTS 入口：实际合成逻辑已迁移到 ``app/tts_providers.py``（provider 注册表 + 适配层）。
本文件**仅**作为 re-export 兼容层，保留 ``synthesize_mimo_tts`` / ``synthesize_tts`` /
``resolve_tts_config`` 等老接口符号。新代码应直接 ``from app.tts_providers import ...``。
"""

from __future__ import annotations

from app.tts_providers import (
    DEFAULT_TTS_VOICE,
    MIMO_TTS_ENDPOINT,
    MIMO_TTS_MODEL,
    MIMO_TTS_VOICES,
    TTS_PROBE_TEXT,
    DanmuTtsError,
    ResolvedTtsConfig,
    clamp_read_interval_sec,
    normalize_tts_voice,
    resolve_tts_config,
    synthesize_tts,
)

__all__ = [
    "DEFAULT_TTS_VOICE",
    "DanmuTtsError",
    "MIMO_TTS_ENDPOINT",
    "MIMO_TTS_MODEL",
    "MIMO_TTS_VOICES",
    "TTS_PROBE_TEXT",
    "ResolvedTtsConfig",
    "clamp_read_interval_sec",
    "normalize_tts_voice",
    "resolve_tts_config",
    "synthesize_mimo_tts",
    "synthesize_tts",
]


def synthesize_mimo_tts(
    api_key: str,
    text: str,
    *,
    style_prompt: str = "",
    voice: str = DEFAULT_TTS_VOICE,
    endpoint: str = MIMO_TTS_ENDPOINT,
    model: str = MIMO_TTS_MODEL,
    timeout_sec: float = 60.0,
    resolved: ResolvedTtsConfig | None = None,
) -> bytes:
    """调用 chat/completions，返回 WAV 字节。"""
    if resolved is None:
        resolved = ResolvedTtsConfig(
            provider="mimo",
            endpoint=endpoint.rstrip("/"),
            model=model,
            is_custom=endpoint != MIMO_TTS_ENDPOINT or model != MIMO_TTS_MODEL,
            stored_provider="",
            stored_endpoint="",
            stored_model_id="",
        )
    return synthesize_tts(
        api_key,
        text,
        resolved=resolved,
        style_prompt=style_prompt,
        voice=voice,
        timeout_sec=timeout_sec,
    )
