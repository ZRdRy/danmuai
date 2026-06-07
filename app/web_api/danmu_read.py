"""读弹幕（MiMo TTS）专用 API；配置不经 PUT /api/config。

路由（由 ``app.web_api.routes`` 注册）：
- ``GET /api/danmu-read``：返回读弹幕配置（api_key 掩码）。
- ``PUT /api/danmu-read``：保存读弹幕配置（enabled/interval/voice/style_prompt/provider/endpoint/model_id/api_key）。
- ``POST /api/danmu-read/probe``：发送试听文本触发 TTS 合成 + 本地播放（不写入配置）。

注册方式：``app.web_api.routes`` 调用 ``register_danmu_read_routes(app, bridge, check_token)``。
所有写操作经 ``WebConsoleBridge.invoke_on_main`` 回到主线程，由 ``DanmuReadService.apply_config`` 落地。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from app.application.config_service import MASKED_API_KEY
from app.danmu_read_service import export_danmu_read_config
from app.danmu_tts import normalize_tts_voice
from app.model_providers import normalize_endpoint
from app.tts_providers import TTS_PROVIDER_CUSTOM_OPENAI

if TYPE_CHECKING:
    from main import DanmuApp


def get_config(app: "DanmuApp") -> dict[str, object]:
    return export_danmu_read_config(app.config)


def save_config(app: "DanmuApp", payload: dict[str, Any]) -> dict[str, object]:
    try:
        return app.apply_danmu_read_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def run_probe(app: "DanmuApp", payload: dict[str, Any] | None = None) -> dict[str, object]:
    overrides: dict[str, str | None] = {
        "api_key_override": None,
        "provider_override": None,
        "endpoint_override": None,
        "model_id_override": None,
    }
    if payload:
        raw = payload.get("api_key")
        if isinstance(raw, str):
            key = raw.strip()
            if key and key != MASKED_API_KEY:
                overrides["api_key_override"] = key
        if "provider" in payload:
            provider = str(payload.get("provider") or "").strip()
            overrides["provider_override"] = provider or TTS_PROVIDER_CUSTOM_OPENAI
        if "endpoint" in payload:
            endpoint = normalize_endpoint(str(payload.get("endpoint") or ""))
            overrides["endpoint_override"] = endpoint
        if "model_id" in payload:
            model_id = str(payload.get("model_id") or "").strip()
            overrides["model_id_override"] = model_id
    return app.run_danmu_read_probe(**overrides)


def normalize_put_payload(body: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "enabled" in body:
        out["enabled"] = bool(body.get("enabled"))
    if "interval_sec" in body:
        out["interval_sec"] = body.get("interval_sec")
    if "voice" in body:
        out["voice"] = normalize_tts_voice(str(body.get("voice") or ""))
    if "style_prompt" in body:
        out["style_prompt"] = str(body.get("style_prompt") or "")
    if "api_key" in body:
        key = str(body.get("api_key") or "").strip()
        if key and key != MASKED_API_KEY:
            out["api_key"] = key
    if "provider" in body:
        out["provider"] = str(body.get("provider") or "").strip()
    if "endpoint" in body:
        out["endpoint"] = normalize_endpoint(str(body.get("endpoint") or ""))
    if "model_id" in body:
        out["model_id"] = str(body.get("model_id") or "").strip()
    return out


def safe_read_api(fn, *args, **kwargs):
    """只读 API：可在 HTTP 线程直接调用（不写入 Config / 不 emit Qt 信号）。"""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
