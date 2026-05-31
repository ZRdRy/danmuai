"""MiMo V2.5 TTS（mimo-v2.5-tts）非流式合成。"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MIMO_TTS_ENDPOINT = "https://api.xiaomimimo.com/v1"
MIMO_TTS_MODEL = "mimo-v2.5-tts"
MIMO_TTS_VOICES: tuple[str, ...] = (
    "mimo_default",
    "冰糖",
    "茉莉",
    "苏打",
    "白桦",
    "Mia",
    "Chloe",
    "Milo",
    "Dean",
)
DEFAULT_TTS_VOICE = "冰糖"
TTS_PROBE_TEXT = "你好，这是一条读弹幕试听。"


class DanmuTtsError(Exception):
    """TTS 请求或响应解析失败。"""


def _extract_http_error_message(exc: httpx.HTTPStatusError) -> str:
    try:
        err_body = exc.response.json()
    except Exception:
        return ""
    if not isinstance(err_body, dict):
        return ""
    message = err_body.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    err = err_body.get("error")
    if isinstance(err, dict):
        nested = err.get("message")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
        code = err.get("code")
        if code is not None:
            return str(code)
    if isinstance(err, str) and err.strip():
        return err.strip()
    return ""


def normalize_tts_voice(voice: str | None) -> str:
    raw = (voice or "").strip()
    if raw in MIMO_TTS_VOICES:
        return raw
    return DEFAULT_TTS_VOICE


def clamp_read_interval_sec(value: object, *, default: int = 10) -> int:
    try:
        sec = int(value)
    except (TypeError, ValueError):
        sec = default
    return max(3, min(sec, 120))


def synthesize_mimo_tts(
    api_key: str,
    text: str,
    *,
    style_prompt: str = "",
    voice: str = DEFAULT_TTS_VOICE,
    endpoint: str = MIMO_TTS_ENDPOINT,
    timeout_sec: float = 60.0,
) -> bytes:
    """调用 chat/completions，返回 WAV 字节。"""
    key = (api_key or "").strip()
    if not key:
        raise DanmuTtsError("未配置 TTS API Key")
    content = (text or "").strip()
    if not content:
        raise DanmuTtsError("朗读文本为空")

    messages: list[dict[str, str]] = []
    style = (style_prompt or "").strip()
    if style:
        messages.append({"role": "user", "content": style})
    messages.append({"role": "assistant", "content": content})

    payload: dict[str, Any] = {
        "model": MIMO_TTS_MODEL,
        "messages": messages,
        "audio": {"format": "wav", "voice": normalize_tts_voice(voice)},
    }
    url = f"{endpoint.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=10.0)) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException as exc:
        raise DanmuTtsError("TTS 请求超时") from exc
    except httpx.HTTPStatusError as exc:
        detail = _extract_http_error_message(exc)
        code = exc.response.status_code
        raise DanmuTtsError(detail or f"TTS HTTP {code}") from exc
    except httpx.HTTPError as exc:
        raise DanmuTtsError(f"TTS 网络错误: {exc}") from exc

    try:
        choices = body.get("choices") or []
        message = choices[0].get("message") or {}
        audio = message.get("audio") or {}
        data_b64 = audio.get("data") or ""
        if not data_b64:
            raise DanmuTtsError("TTS 响应无音频数据")
        return base64.b64decode(data_b64)
    except DanmuTtsError:
        raise
    except Exception as exc:
        logger.debug("tts response parse failed: %s", exc)
        raise DanmuTtsError("TTS 响应解析失败") from exc
