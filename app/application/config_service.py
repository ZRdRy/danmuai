"""Web PUT /api/config 的业务写入入口：校验、归一化后写 ConfigStore 并 emit config_changed。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from main import DanmuApp


MASKED_API_KEY = "********"

WEB_CONFIG_KEYS = (
    "api_endpoint",
    "api_mode",
    "model",
    "temperature",
    "max_tokens",
    "danmu_speed",
    "danmu_lines",
    "danmu_max_chars",
    "dedup_threshold",
    "screen_index",
    "layout_mode",
    "opacity",
    "font_size",
    "empty_accel",
    "eviction_mode",
    "image_max_width",
    "image_quality",
    "hotkey",
    "memory_mode",
    "memory_window",
    "mic_mode_enabled",
    "mic_window_sec",
    "normal_recognition_interval_sec",
    "normal_reply_count",
)


def normalize_legacy_display_mode(items: dict[str, str]) -> None:
    """Map removed realtime display mode to normal on Web config patch."""
    mode = str(items.get("danmu_display_mode", "")).strip().lower()
    if mode == "realtime":
        items["danmu_display_mode"] = "normal"


def _clamp_choice(
    items: dict[str, str],
    key: str,
    allowed: tuple[str, ...],
    default: str,
) -> None:
    if key not in items:
        return
    value = str(items[key]).strip().lower()
    items[key] = value if value in allowed else default


def _clamp_int_key(
    items: dict[str, str],
    key: str,
    default: int,
    min_value: int,
    max_value: int,
) -> None:
    if key not in items:
        return
    try:
        value = int(items[key])
        items[key] = str(max(min_value, min(value, max_value)))
    except (TypeError, ValueError):
        items[key] = str(default)


def _submitted_api_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key or key == MASKED_API_KEY:
        return ""
    return key


def _custom_model_identity(model: dict[str, Any]) -> tuple[str, str]:
    return (
        str(model.get("modelId") or model.get("model") or "").strip(),
        str(model.get("name") or "").strip(),
    )


def set_default_model_selection(
    config,
    model_id: str,
    *,
    sync_legacy_model: bool = True,
) -> str:
    """同时维护 default_model_id 与 legacy model 键，避免 Web/自定义模型路径双写不一致。"""
    normalized = str(model_id or "").strip()
    if not normalized:
        return ""
    config.set_default_model_id(normalized)
    if sync_legacy_model:
        config.set("model", normalized)
    return normalized


class ConfigService:
    """DanmuApp.apply_web_config_payload 的委托实现；勿在 web_console 路由内直接 set_batch。"""

    def __init__(self, app: "DanmuApp"):
        self._app = app
        self._config = app.config

    def apply_web_payload(self, payload: dict[str, Any]) -> None:
        """仅接受 WEB_CONFIG_KEYS 子集 + api_key / custom_models / active_personae；经 ConfigStore 写缓存，不直连 SQLite 连接对象。"""
        items: dict[str, str] = {}
        for key in WEB_CONFIG_KEYS:
            if key in payload and payload[key] is not None:
                items[key] = str(payload[key])

        legacy_mode = payload.get("danmu_display_mode")
        if legacy_mode is not None:
            normalize_legacy_display_mode({"danmu_display_mode": str(legacy_mode)})
            if str(legacy_mode).strip().lower() == "realtime":
                self._config.set("danmu_display_mode", "normal")

        if items:
            self._normalize_items(items)
            self._config.set_batch(items)
            model_id = (items.get("model") or "").strip()
            if model_id:
                set_default_model_selection(self._config, model_id, sync_legacy_model=False)

        api_key = _submitted_api_key(payload.get("api_key", ""))
        if api_key:
            self._config.set_api_key(api_key)

        if "default_model_id" in payload:
            set_default_model_selection(self._config, payload.get("default_model_id", ""))

        custom_models = payload.get("custom_models")
        if isinstance(custom_models, list):
            self._config.set_custom_models(self._merge_custom_models(custom_models))

        active = payload.get("active_personae")
        if isinstance(active, list) and active:
            self._app.personae.set_active([str(name) for name in active])

        self._app.config_changed.emit()

    def _normalize_items(self, items: dict[str, str]) -> None:
        items["region_x"] = "0"
        items["region_y"] = "0"
        items["region_w"] = "0"
        items["region_h"] = "0"

        if "mic_window_sec" in items:
            from app.mic_buffer import clamp_mic_window_sec

            try:
                items["mic_window_sec"] = str(clamp_mic_window_sec(int(items["mic_window_sec"])))
            except (TypeError, ValueError):
                items["mic_window_sec"] = "5"

        if "danmu_max_chars" in items:
            from app.danmu_engine import DANMU_MAX_CHARS_MAX, DANMU_MAX_CHARS_MIN

            try:
                value = int(items["danmu_max_chars"])
                items["danmu_max_chars"] = str(max(DANMU_MAX_CHARS_MIN, min(value, DANMU_MAX_CHARS_MAX)))
            except (TypeError, ValueError):
                items["danmu_max_chars"] = "15"

        if "danmu_lines" in items:
            from app.danmu_engine import DEFAULT_DANMU_LINES, clamp_danmu_lines

            try:
                items["danmu_lines"] = str(clamp_danmu_lines(int(items["danmu_lines"])))
            except (TypeError, ValueError):
                items["danmu_lines"] = str(DEFAULT_DANMU_LINES)

        if "layout_mode" in items:
            from app.danmu_engine import normalize_layout_mode

            items["layout_mode"] = normalize_layout_mode(items["layout_mode"])

        if "normal_recognition_interval_sec" in items or "normal_reply_count" in items:
            from app.personae import DEFAULT_NORMAL_REPLY_COUNT

            _clamp_int_key(items, "normal_recognition_interval_sec", 5, 1, 60)
            _clamp_int_key(items, "normal_reply_count", DEFAULT_NORMAL_REPLY_COUNT, 1, 20)

        if "memory_mode" in items or "memory_window" in items:
            _clamp_choice(
                items,
                "memory_mode",
                ("off", "dedup_only", "scene_card", "strong"),
                "off",
            )
            _clamp_int_key(items, "memory_window", 10, 1, 20)

    def _merge_custom_models(self, payload_models: list[Any]) -> list[dict[str, Any]]:
        from app.web_api.custom_models import MASKED_KEY

        existing = [model for model in self._config.get_custom_models() if isinstance(model, dict)]
        existing_by_identity = {
            _custom_model_identity(model): model
            for model in existing
            if any(_custom_model_identity(model))
        }
        merged: list[dict[str, Any]] = []
        for index, incoming in enumerate(payload_models):
            if not isinstance(incoming, dict):
                continue
            row = dict(incoming)
            key = (row.get("apiKey") or row.get("api_key") or "").strip()
            previous = existing_by_identity.get(_custom_model_identity(row))
            if previous is None and index < len(existing):
                previous = existing[index]
            if key == MASKED_KEY and previous:
                row["apiKey"] = previous.get("apiKey", "")
            elif key == MASKED_KEY:
                row["apiKey"] = ""
            merged.append(row)
        return merged


def apply_web_config_patch(app: "DanmuApp", payload: dict[str, Any]) -> None:
    ConfigService(app).apply_web_payload(payload)
