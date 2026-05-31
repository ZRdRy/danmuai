"""读弹幕（MiMo TTS）专用 API；配置不经 PUT /api/config。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.config_service import MASKED_API_KEY
from app.danmu_read_service import export_danmu_read_config
from app.danmu_tts import normalize_tts_voice

if TYPE_CHECKING:
    from main import DanmuApp


def get_config(app: "DanmuApp") -> dict[str, object]:
    return export_danmu_read_config(app.config)


def save_config(app: "DanmuApp", payload: dict[str, Any]) -> dict[str, object]:
    return app.apply_danmu_read_config(payload)


def run_probe(app: "DanmuApp", payload: dict[str, Any] | None = None) -> dict[str, object]:
    override = None
    if payload:
        raw = payload.get("api_key")
        if isinstance(raw, str):
            key = raw.strip()
            if key and key != MASKED_API_KEY:
                override = key
    return app.run_danmu_read_probe(api_key_override=override)


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
    return out
