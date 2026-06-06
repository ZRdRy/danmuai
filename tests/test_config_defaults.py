from app.application.config_service import (
    WEB_CONFIG_KEYS,
    _clamp_choice,
    _clamp_int_key,
)
from app.config_defaults import (
    CONFIG_DEFAULTS,
    DEFAULT_LANGUAGE,
    seed_config_defaults,
)
from app.config_store import ConfigStore


def test_seed_includes_language_field_when_added(tmp_path):
    store = ConfigStore(db_path=tmp_path / "config.db")
    store.set("language", "")

    seed_config_defaults(store)

    assert store.get("language") == DEFAULT_LANGUAGE
    store.close()


# W-FP-001：display_mode 与悬浮窗基础配置字段
FP_KEYS = (
    "display_mode",
    "floating_panel_opacity",
    "floating_panel_font_size",
    "floating_panel_max_items",
    "floating_panel_speed",
    "floating_panel_click_through",
)


def test_fp_keys_present_in_defaults():
    """6 个 W-FP-001 字段在 CONFIG_DEFAULTS 中均有默认值。"""
    for key in FP_KEYS:
        assert key in CONFIG_DEFAULTS, f"missing default for {key}"
        assert CONFIG_DEFAULTS[key] != ""


def test_fp_keys_present_in_web_config_keys():
    """6 个 W-FP-001 字段在 WEB_CONFIG_KEYS 元组中可被 Web 端读写。"""
    for key in FP_KEYS:
        assert key in WEB_CONFIG_KEYS, f"missing web key for {key}"


def test_seed_writes_fp_defaults_on_blank_db(tmp_path):
    """空 DB seed 后 6 个新键均落库为默认值。"""
    store = ConfigStore(db_path=tmp_path / "config.db")
    for key in FP_KEYS:
        store.set(key, "")
    seed_config_defaults(store)
    for key in FP_KEYS:
        assert store.get(key) == CONFIG_DEFAULTS[key], key
    store.close()


def test_display_mode_invalid_falls_back_to_overlay():
    """display_mode 非法值经 _clamp_choice 回落为 overlay。"""
    items = {"display_mode": "weird-mode"}
    _clamp_choice(items, "display_mode", ("overlay", "floating_panel", "both"), "overlay")
    assert items["display_mode"] == "overlay"


def test_display_mode_both_passes_through():
    items = {"display_mode": "BOTH"}
    _clamp_choice(items, "display_mode", ("overlay", "floating_panel", "both"), "overlay")
    assert items["display_mode"] == "both"


def test_floating_panel_max_items_clamped():
    """floating_panel_max_items=9999 被钳到 200。"""
    items = {"floating_panel_max_items": "9999"}
    _clamp_int_key(items, "floating_panel_max_items", 60, 5, 200)
    assert items["floating_panel_max_items"] == "200"


def test_floating_panel_font_size_clamped_min():
    items = {"floating_panel_font_size": "1"}
    _clamp_int_key(items, "floating_panel_font_size", 18, 12, 48)
    assert items["floating_panel_font_size"] == "12"


def test_floating_panel_opacity_zero_allowed():
    items = {"floating_panel_opacity": "0"}
    _clamp_int_key(items, "floating_panel_opacity", 85, 0, 100)
    assert items["floating_panel_opacity"] == "0"
