"""Default config values for export and first-run seeding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.personae import DEFAULT_NORMAL_REPLY_COUNT

if TYPE_CHECKING:
    from app.config_store import ConfigStore

# Numeric fallbacks when a key is missing from the store (keep in sync with CONFIG_DEFAULTS).
DEFAULT_DANMU_SPEED = 2.0
DEFAULT_FONT_SIZE = 24
DEFAULT_DEDUP_THRESHOLD = 0.5
DEFAULT_IMAGE_MAX_WIDTH = 768
DEFAULT_LANGUAGE = "zh"

# String values aligned with runtime fallbacks in main.py / danmu_engine / ai_client.
CONFIG_DEFAULTS: dict[str, str] = {
    "api_mode": "doubao",
    "temperature": "0.7",
    "max_tokens": "512",
    "use_thinking": "0",
    "danmu_speed": "2",
    "danmu_lines": "20",
    "danmu_max_chars": "15",
    "dedup_threshold": "0.5",
    "screen_index": "0",
    "layout_mode": "fullscreen",
    "opacity": "100",
    "font_size": "24",
    "danmu_pool_enabled": "1",
    "danmu_pool_use_custom": "0",
    "min_on_screen": "5",
    "empty_accel": "1",
    "eviction_mode": "natural",
    "image_max_width": "768",
    "image_quality": "85",
    "hotkey": "Ctrl+Shift+B",
    "language": DEFAULT_LANGUAGE,
    "memory_mode": "off",
    "memory_window": "10",
    "mic_mode_enabled": "0",
    "mic_window_sec": "5",
    "normal_recognition_interval_sec": "5",
    "normal_reply_count": str(DEFAULT_NORMAL_REPLY_COUNT),
    "danmu_read_enabled": "0",
    "danmu_read_interval_sec": "10",
    "tts_voice": "冰糖",
    "tts_style_prompt": (
        "温柔微颤语气，1.0倍速，温暖音色，独白式表达，"
        "句尾轻收配合自然呼吸停顿，情绪克制有层次，适配泪目治愈类弹幕"
    ),
}

# 首装工厂默认服务商（与 model_providers doubao 预设一致）
_DEFAULT_PROVIDER_ID = "doubao"


def _default_api_endpoint() -> str:
    from app.model_providers import get_provider

    spec = get_provider(_DEFAULT_PROVIDER_ID)
    return spec.default_endpoint if spec else ""


def _default_model_id() -> str:
    from app.model_catalog import default_catalog_model_id

    return default_catalog_model_id(_DEFAULT_PROVIDER_ID)


def export_web_config_defaults() -> dict[str, str]:
    """Web「恢复默认」唯一来源：覆盖 WEB_CONFIG_KEYS，不含 api_key / 自定义模型 / 人格 / 识图区域。

    修改默认值时须同步 CONFIG_DEFAULTS 与 main.py / danmu_engine 等 runtime fallback。
    """
    from app.application.config_service import WEB_CONFIG_KEYS

    defaults = {key: CONFIG_DEFAULTS.get(key, "") for key in WEB_CONFIG_KEYS}
    defaults["api_endpoint"] = _default_api_endpoint()
    default_model = _default_model_id()
    defaults["model"] = default_model
    return defaults


def config_value_with_default(config, key: str) -> str:
    """Return stored value or documented default (for API export / UI)."""
    val = config.get(key, "")
    if val != "":
        return val
    return CONFIG_DEFAULTS.get(key, "")


def seed_config_defaults(config: "ConfigStore") -> None:
    """Persist defaults for keys that are missing or blank."""
    items = {
        key: default
        for key, default in CONFIG_DEFAULTS.items()
        if not config.get(key, "")
    }
    if items:
        config.set_batch(items)
