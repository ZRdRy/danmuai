"""读弹幕 TTS provider 注册表与适配层（MiMo 默认 + OpenAI-compat chat/audio）。

MiMo TTS + 播放链路：
1. ``DanmuReadService._pick_and_synthesize`` 抽样一条可见弹幕 → ``resolve_tts_config``。
2. ``synthesize_tts`` 按 ``resolved.provider`` 选 adapter：
   - ``mimo``：``MimoTtsAdapter`` → MiMo ``/chat/completions`` + ``audio: {format: wav, voice: ...}``，
     voice 走 ``MIMO_TTS_VOICES`` 白名单。
   - ``custom_openai``：``OpenAiCompatAudioTtsAdapter`` → 同结构，voice 字段自由。
3. 响应 ``choices[0].message.audio.data``（base64 WAV）→ ``DanmuTtsPlayback.play_wav_bytes``。

新增 provider：实现 ``TtsSynthesisAdapter`` 子类并注册到 ``_ADAPTERS``；不需改主链路。
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.model_providers import is_valid_endpoint, normalize_endpoint
from app.tts_audio_utils import ensure_wav_bytes, pcm_to_wav

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

TTS_PROVIDER_MIMO = "mimo"
TTS_PROVIDER_DOUBAO = "doubao"
TTS_PROVIDER_DASHSCOPE_QWEN = "dashscope_qwen"
TTS_PROVIDER_CUSTOM_OPENAI = "custom_openai"

_PRESET_TTS_PROVIDERS = frozenset(
    {TTS_PROVIDER_MIMO, TTS_PROVIDER_DOUBAO, TTS_PROVIDER_DASHSCOPE_QWEN}
)


class DanmuTtsError(Exception):
    """TTS 请求或响应解析失败。"""


def tts_audio_unsupported_message(model_id: str) -> str:
    """读弹幕为 TTS 链路；普通 chat 模型响应无 message.audio.data 时提示用户。"""
    mid = (model_id or "").strip() or "?"
    return (
        f"当前 provider/model「{mid}」不支持读弹幕 TTS 音频输出。"
        "请使用支持 chat/completions 且响应含 message.audio.data 的 TTS 模型"
        "（如小米 MiMo mimo-v2.5-tts）；普通聊天/视觉模型无法朗读。"
    )


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


def normalize_tts_voice(
    voice: str | None,
    *,
    provider: str = TTS_PROVIDER_MIMO,
    model_id: str = "",
) -> str:
    from app.tts_catalog import normalize_catalog_voice

    pid = (provider or TTS_PROVIDER_MIMO).strip() or TTS_PROVIDER_MIMO
    if pid == TTS_PROVIDER_MIMO and not model_id:
        raw = (voice or "").strip()
        if raw in MIMO_TTS_VOICES:
            return raw
        return DEFAULT_TTS_VOICE
    if pid in _PRESET_TTS_PROVIDERS and pid != TTS_PROVIDER_MIMO:
        from app.tts_catalog import default_model_for_provider

        mid = (model_id or "").strip() or default_model_for_provider(pid)
        return normalize_catalog_voice(voice, provider_id=pid, model_id=mid)
    raw = (voice or "").strip()
    return raw or DEFAULT_TTS_VOICE


def clamp_read_interval_sec(value: object, *, default: int = 10) -> int:
    try:
        sec = int(value)
    except (TypeError, ValueError):
        sec = default
    return max(3, min(sec, 120))


@dataclass(frozen=True)
class TtsProviderSpec:
    id: str
    label_zh: str
    default_endpoint: str
    default_model: str


TTS_PROVIDERS: tuple[TtsProviderSpec, ...] = (
    TtsProviderSpec(
        id=TTS_PROVIDER_MIMO,
        label_zh="小米 MiMo（默认）",
        default_endpoint=MIMO_TTS_ENDPOINT,
        default_model=MIMO_TTS_MODEL,
    ),
    TtsProviderSpec(
        id=TTS_PROVIDER_DOUBAO,
        label_zh="火山豆包语音",
        default_endpoint="https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        default_model="seed-tts-2.0",
    ),
    TtsProviderSpec(
        id=TTS_PROVIDER_DASHSCOPE_QWEN,
        label_zh="阿里百炼 Qwen3",
        default_endpoint="https://dashscope.aliyuncs.com/api/v1",
        default_model="qwen3-tts-flash-2025-11-27",
    ),
    TtsProviderSpec(
        id=TTS_PROVIDER_CUSTOM_OPENAI,
        label_zh="自定义（OpenAI 兼容）",
        default_endpoint="",
        default_model="",
    ),
)

_TTS_PROVIDER_BY_ID = {p.id: p for p in TTS_PROVIDERS}


@dataclass(frozen=True)
class ResolvedTtsConfig:
    provider: str
    endpoint: str
    model: str
    is_custom: bool
    stored_provider: str
    stored_endpoint: str
    stored_model_id: str
    app_id: str = ""


def get_tts_provider(provider_id: str) -> TtsProviderSpec | None:
    return _TTS_PROVIDER_BY_ID.get((provider_id or "").strip())


def _stored_custom_fields(config) -> tuple[str, str, str]:
    provider = (config.get("tts_provider") or "").strip()
    endpoint = normalize_endpoint(config.get("tts_endpoint") or "")
    model_id = (config.get("tts_model_id") or "").strip()
    return provider, endpoint, model_id


def is_custom_tts_config(provider: str, endpoint: str, model_id: str) -> bool:
    if (provider or "").strip() in _PRESET_TTS_PROVIDERS - {TTS_PROVIDER_MIMO}:
        return True
    return bool(provider or endpoint or model_id)


def validate_custom_tts_fields(
    provider: str,
    endpoint: str,
    model_id: str,
) -> None:
    """按 provider 校验 TTS 配置字段。"""
    pid = (provider or "").strip()
    if not is_custom_tts_config(pid, endpoint, model_id):
        return
    if pid == TTS_PROVIDER_DOUBAO:
        if not model_id:
            raise ValueError("请选择豆包语音模型版本")
        return
    if pid == TTS_PROVIDER_DASHSCOPE_QWEN:
        if not model_id:
            raise ValueError("请选择百炼 Qwen3 模型")
        return
    if not endpoint:
        raise ValueError("API 地址不能为空")
    if not model_id:
        raise ValueError("模型名称不能为空")
    if not is_valid_endpoint(endpoint):
        raise ValueError("API 地址格式无效")


def resolve_tts_config(
    config,
    *,
    provider_override: str | None = None,
    endpoint_override: str | None = None,
    model_id_override: str | None = None,
) -> ResolvedTtsConfig:
    from app.tts_catalog import DOUBAO_TTS_URL, default_model_for_provider

    stored_provider, stored_endpoint, stored_model_id = _stored_custom_fields(config)
    provider = (provider_override if provider_override is not None else stored_provider).strip()
    endpoint = normalize_endpoint(
        endpoint_override if endpoint_override is not None else stored_endpoint
    )
    model_id = (
        (model_id_override if model_id_override is not None else stored_model_id) or ""
    ).strip()
    app_id = (config.get("tts_app_id") or "").strip()

    if not is_custom_tts_config(provider, endpoint, model_id):
        default = get_tts_provider(TTS_PROVIDER_MIMO)
        assert default is not None
        return ResolvedTtsConfig(
            provider=TTS_PROVIDER_MIMO,
            endpoint=default.default_endpoint,
            model=default.default_model,
            is_custom=False,
            stored_provider="",
            stored_endpoint="",
            stored_model_id="",
        )

    validate_custom_tts_fields(provider, endpoint, model_id)
    resolved_provider = provider or TTS_PROVIDER_CUSTOM_OPENAI

    if resolved_provider == TTS_PROVIDER_DOUBAO:
        spec = get_tts_provider(TTS_PROVIDER_DOUBAO)
        assert spec is not None
        resolved_model = model_id or default_model_for_provider(TTS_PROVIDER_DOUBAO)
        return ResolvedTtsConfig(
            provider=TTS_PROVIDER_DOUBAO,
            endpoint=DOUBAO_TTS_URL,
            model=resolved_model,
            is_custom=True,
            stored_provider=provider,
            stored_endpoint="",
            stored_model_id=resolved_model,
            app_id=app_id,
        )

    if resolved_provider == TTS_PROVIDER_DASHSCOPE_QWEN:
        spec = get_tts_provider(TTS_PROVIDER_DASHSCOPE_QWEN)
        assert spec is not None
        resolved_model = model_id or default_model_for_provider(TTS_PROVIDER_DASHSCOPE_QWEN)
        return ResolvedTtsConfig(
            provider=TTS_PROVIDER_DASHSCOPE_QWEN,
            endpoint=spec.default_endpoint,
            model=resolved_model,
            is_custom=True,
            stored_provider=provider,
            stored_endpoint="",
            stored_model_id=resolved_model,
        )

    return ResolvedTtsConfig(
        provider=resolved_provider,
        endpoint=endpoint,
        model=model_id,
        is_custom=True,
        stored_provider=provider,
        stored_endpoint=endpoint,
        stored_model_id=model_id,
    )


class TtsSynthesisAdapter(Protocol):
    def synthesize(
        self,
        api_key: str,
        text: str,
        *,
        resolved: ResolvedTtsConfig,
        style_prompt: str = "",
        voice: str = DEFAULT_TTS_VOICE,
        timeout_sec: float = 60.0,
    ) -> bytes:
        ...


def _build_chat_audio_payload(
    resolved: ResolvedTtsConfig,
    text: str,
    *,
    style_prompt: str,
    voice: str,
    normalize_voice: bool,
) -> dict[str, Any]:
    content = (text or "").strip()
    if not content:
        raise DanmuTtsError("朗读文本为空")

    messages: list[dict[str, str]] = []
    style = (style_prompt or "").strip()
    if style:
        messages.append({"role": "user", "content": style})
    messages.append({"role": "assistant", "content": content})

    voice_value = (
        normalize_tts_voice(voice, provider=resolved.provider, model_id=resolved.model)
        if normalize_voice
        else (voice or DEFAULT_TTS_VOICE).strip()
    )
    return {
        "model": resolved.model,
        "messages": messages,
        "audio": {"format": "wav", "voice": voice_value},
    }


def _post_chat_audio(
    api_key: str,
    resolved: ResolvedTtsConfig,
    payload: dict[str, Any],
    *,
    timeout_sec: float,
) -> bytes:
    key = (api_key or "").strip()
    if not key:
        raise DanmuTtsError("未配置 TTS API Key")

    url = f"{resolved.endpoint.rstrip('/')}/chat/completions"
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
        return _decode_audio_wav_from_body(body, model_id=resolved.model)
    except DanmuTtsError:
        raise
    except Exception as exc:
        logger.debug("tts response parse failed: %s", exc)
        raise DanmuTtsError("TTS 响应解析失败") from exc


def _decode_audio_wav_from_body(body: dict[str, Any], *, model_id: str) -> bytes:
    """解析 chat/completions 响应中的 base64 WAV；文本-only 响应给出 TTS 能力提示。"""
    choices = body.get("choices") or []
    if not choices:
        raise DanmuTtsError("TTS 响应无音频数据")
    message = choices[0].get("message") or {}
    audio = message.get("audio") or {}
    data_b64 = audio.get("data") or ""
    if data_b64:
        return base64.b64decode(data_b64)
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        raise DanmuTtsError(tts_audio_unsupported_message(model_id))
    raise DanmuTtsError("TTS 响应无音频数据")


class MimoTtsAdapter:
    def synthesize(
        self,
        api_key: str,
        text: str,
        *,
        resolved: ResolvedTtsConfig,
        style_prompt: str = "",
        voice: str = DEFAULT_TTS_VOICE,
        timeout_sec: float = 60.0,
    ) -> bytes:
        payload = _build_chat_audio_payload(
            resolved,
            text,
            style_prompt=style_prompt,
            voice=voice,
            normalize_voice=True,
        )
        return _post_chat_audio(api_key, resolved, payload, timeout_sec=timeout_sec)


class OpenAiCompatAudioTtsAdapter:
    """OpenAI-compat chat/completions + message.audio.data（与 MiMo TTS 同结构）。"""

    def synthesize(
        self,
        api_key: str,
        text: str,
        *,
        resolved: ResolvedTtsConfig,
        style_prompt: str = "",
        voice: str = DEFAULT_TTS_VOICE,
        timeout_sec: float = 60.0,
    ) -> bytes:
        payload = _build_chat_audio_payload(
            resolved,
            text,
            style_prompt=style_prompt,
            voice=voice,
            normalize_voice=False,
        )
        return _post_chat_audio(api_key, resolved, payload, timeout_sec=timeout_sec)


def _doubao_append_line(chunks: list[bytes], line: bytes) -> None:
    line = line.strip()
    if not line:
        return
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return
    code = obj.get("code")
    if code == 0 and obj.get("data"):
        chunks.append(base64.b64decode(obj["data"]))
    elif code not in (0, 20000000, None) and code is not None:
        msg = obj.get("message") or str(code)
        raise DanmuTtsError(f"豆包 TTS: {msg}")


class DoubaoTtsAdapter:
    """火山豆包 V3 单向流式 HTTP TTS。"""

    def synthesize(
        self,
        api_key: str,
        text: str,
        *,
        resolved: ResolvedTtsConfig,
        style_prompt: str = "",
        voice: str = DEFAULT_TTS_VOICE,
        timeout_sec: float = 60.0,
    ) -> bytes:
        from app.tts_catalog import infer_doubao_resource_id, model_supports_style

        key = (api_key or "").strip()
        app_id = (resolved.app_id or "").strip()
        if not key:
            raise DanmuTtsError("未配置豆包 TTS API Key（或 Access Token）")

        speaker = normalize_tts_voice(
            voice, provider=TTS_PROVIDER_DOUBAO, model_id=resolved.model
        )
        resource_id = resolved.model or infer_doubao_resource_id(speaker)
        payload: dict[str, Any] = {
            "user": {"uid": str(uuid.uuid4())},
            "req_params": {
                "text": (text or "").strip(),
                "speaker": speaker,
                "audio_params": {"format": "pcm", "sample_rate": 24000},
            },
        }
        style = (style_prompt or "").strip()
        if style and model_supports_style(TTS_PROVIDER_DOUBAO, resolved.model):
            payload["req_params"]["additions"] = json.dumps(
                {"context_texts": [style]}, ensure_ascii=False
            )

        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        if app_id and key:
            headers["X-Api-App-Id"] = app_id
            headers["X-Api-Access-Key"] = key
        elif key:
            headers["X-Api-Key"] = key
        else:
            raise DanmuTtsError("豆包 TTS 需配置 API Key，或 App ID + Access Token")

        url = resolved.endpoint or "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=15.0)) as client:
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = resp.read()
                        raise DanmuTtsError(
                            f"豆包 TTS HTTP {resp.status_code}: {body[:300]!r}"
                        )
                    chunks: list[bytes] = []
                    buf = b""
                    for part in resp.iter_bytes():
                        buf += part
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            _doubao_append_line(chunks, line)
                    if buf.strip():
                        _doubao_append_line(chunks, buf)
                    pcm = b"".join(chunks)
        except DanmuTtsError:
            raise
        except httpx.TimeoutException as exc:
            raise DanmuTtsError("豆包 TTS 请求超时") from exc
        except httpx.HTTPError as exc:
            raise DanmuTtsError(f"豆包 TTS 网络错误: {exc}") from exc

        if len(pcm) < 100:
            raise DanmuTtsError("豆包 TTS 音频过短")
        return pcm_to_wav(pcm)


class QwenTtsHttpAdapter:
    """百炼 Qwen3 非实时 HTTP TTS。"""

    def synthesize(
        self,
        api_key: str,
        text: str,
        *,
        resolved: ResolvedTtsConfig,
        style_prompt: str = "",
        voice: str = DEFAULT_TTS_VOICE,
        timeout_sec: float = 60.0,
    ) -> bytes:
        key = (api_key or "").strip()
        if not key:
            raise DanmuTtsError("未配置百炼 API Key")
        try:
            import dashscope
            from dashscope import MultiModalConversation
        except ImportError as exc:
            raise DanmuTtsError("未安装 dashscope，请 pip install dashscope") from exc

        dashscope.api_key = key
        voice_id = normalize_tts_voice(
            voice, provider=TTS_PROVIDER_DASHSCOPE_QWEN, model_id=resolved.model
        )
        content = (text or "").strip()
        if not content:
            raise DanmuTtsError("朗读文本为空")

        try:
            response = MultiModalConversation.call(
                model=resolved.model,
                api_key=key,
                text=content,
                voice=voice_id,
                language_type="Chinese",
                stream=False,
            )
        except Exception as exc:
            raise DanmuTtsError(f"百炼 TTS 请求失败: {exc}") from exc

        if getattr(response, "status_code", None) != 200:
            raise DanmuTtsError(
                getattr(response, "message", None)
                or f"百炼 TTS HTTP {getattr(response, 'status_code', '?')}"
            )

        output = getattr(response, "output", None) or {}
        audio = output.get("audio") if isinstance(output, dict) else getattr(output, "audio", None)
        if not audio:
            raise DanmuTtsError("百炼 TTS 响应无音频")

        url = audio.get("url") if isinstance(audio, dict) else getattr(audio, "url", "")
        if url:
            try:
                with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=10.0)) as client:
                    r = client.get(url)
                    r.raise_for_status()
                    return ensure_wav_bytes(r.content)
            except httpx.HTTPError as exc:
                raise DanmuTtsError(f"百炼音频下载失败: {exc}") from exc

        data_b64 = audio.get("data") if isinstance(audio, dict) else getattr(audio, "data", "")
        if data_b64:
            return ensure_wav_bytes(base64.b64decode(data_b64))
        raise DanmuTtsError("百炼 TTS 响应无音频 URL 或数据")


class QwenTtsRealtimeAdapter:
    """百炼 Qwen3 实时 WebSocket TTS（整句提交）。"""

    def synthesize(
        self,
        api_key: str,
        text: str,
        *,
        resolved: ResolvedTtsConfig,
        style_prompt: str = "",
        voice: str = DEFAULT_TTS_VOICE,
        timeout_sec: float = 60.0,
    ) -> bytes:
        import time

        key = (api_key or "").strip()
        if not key:
            raise DanmuTtsError("未配置百炼 API Key")
        content = (text or "").strip()
        if not content:
            raise DanmuTtsError("朗读文本为空")

        try:
            import dashscope
            from dashscope.audio.qwen_tts_realtime import (
                AudioFormat,
                QwenTtsRealtime,
                QwenTtsRealtimeCallback,
            )
        except ImportError as exc:
            raise DanmuTtsError("未安装 dashscope，请 pip install dashscope>=1.24.6") from exc

        from app.tts_catalog import model_supports_style

        dashscope.api_key = key
        voice_id = normalize_tts_voice(
            voice, provider=TTS_PROVIDER_DASHSCOPE_QWEN, model_id=resolved.model
        )
        pcm_chunks: list[bytes] = []
        state = {"closed": False, "error": ""}

        class _Cb(QwenTtsRealtimeCallback):
            def on_open(self) -> None:
                pass

            def on_close(self, close_status_code, close_msg) -> None:
                state["closed"] = True

            def on_event(self, response: dict) -> None:
                typ = response.get("type", "")
                if typ == "response.audio.delta":
                    delta = response.get("delta", "")
                    if delta:
                        pcm_chunks.append(base64.b64decode(delta))
                elif typ == "error":
                    state["error"] = str(response.get("error", response))

        callback = _Cb()
        client = QwenTtsRealtime(
            model=resolved.model,
            callback=callback,
            url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        )
        session_kwargs: dict[str, Any] = {
            "voice": voice_id,
            "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
            "mode": "server_commit",
        }
        style = (style_prompt or "").strip()
        if style and model_supports_style(TTS_PROVIDER_DASHSCOPE_QWEN, resolved.model):
            session_kwargs["instructions"] = style
            session_kwargs["optimize_instructions"] = True

        try:
            client.connect()
            client.update_session(**session_kwargs)
            client.append_text(content)
            client.finish()
            t0 = time.perf_counter()
            while not state["closed"] and (time.perf_counter() - t0) < timeout_sec:
                time.sleep(0.05)
        except Exception as exc:
            raise DanmuTtsError(f"百炼实时 TTS 失败: {exc}") from exc

        if state["error"]:
            raise DanmuTtsError(state["error"])
        if not pcm_chunks:
            raise DanmuTtsError("百炼实时 TTS 无音频数据")
        return pcm_to_wav(b"".join(pcm_chunks))


_ADAPTERS: dict[str, TtsSynthesisAdapter] = {
    TTS_PROVIDER_MIMO: MimoTtsAdapter(),
    TTS_PROVIDER_DOUBAO: DoubaoTtsAdapter(),
    TTS_PROVIDER_DASHSCOPE_QWEN: QwenTtsHttpAdapter(),
    TTS_PROVIDER_CUSTOM_OPENAI: OpenAiCompatAudioTtsAdapter(),
}


def get_qwen_tts_adapter(model_id: str) -> TtsSynthesisAdapter:
    if (model_id or "").endswith("-realtime"):
        return QwenTtsRealtimeAdapter()
    return QwenTtsHttpAdapter()


def get_tts_adapter(provider_id: str, *, model_id: str = "") -> TtsSynthesisAdapter:
    pid = (provider_id or "").strip()
    if pid == TTS_PROVIDER_DASHSCOPE_QWEN:
        return get_qwen_tts_adapter(model_id)
    adapter = _ADAPTERS.get(pid)
    if adapter is not None:
        return adapter
    return _ADAPTERS[TTS_PROVIDER_CUSTOM_OPENAI]


def synthesize_tts(
    api_key: str,
    text: str,
    *,
    resolved: ResolvedTtsConfig,
    style_prompt: str = "",
    voice: str = DEFAULT_TTS_VOICE,
    timeout_sec: float = 60.0,
) -> bytes:
    adapter = get_tts_adapter(resolved.provider, model_id=resolved.model)
    return adapter.synthesize(
        api_key,
        text,
        resolved=resolved,
        style_prompt=style_prompt,
        voice=voice,
        timeout_sec=timeout_sec,
    )
