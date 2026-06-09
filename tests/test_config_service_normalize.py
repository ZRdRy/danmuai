"""ConfigService._normalize_items 分支测试（W-TEST-CONFIG-NORMALIZE-001）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.application.config_service import MASKED_API_KEY, ConfigService
from app.config_store import ConfigStore


@pytest.fixture
def config_service(tmp_path):
    config = ConfigStore(db_path=tmp_path / "normalize.db")
    app = SimpleNamespace(
        config=config,
        personae=MagicMock(),
        config_changed=MagicMock(),
    )
    return ConfigService(app)


def test_normalize_font_size_clamped(config_service):
    items = {"font_size": "9999"}
    config_service._normalize_items(items)
    assert items["font_size"] == "72"


def test_normalize_danmu_render_mode_invalid_defaults_scrolling(config_service):
    items = {"danmu_render_mode": "invalid_mode"}
    config_service._normalize_items(items)
    assert items["danmu_render_mode"] == "scrolling"


def test_normalize_pet_scale_clamped(config_service):
    items = {"pet_scale": "9.9"}
    config_service._normalize_items(items)
    assert items["pet_scale"] == "2.0"


def test_normalize_scene_memory_flags_invalid_defaults(config_service):
    items = {
        "scene_memory_enabled": "evil",
        "prompt_dedup_enabled": "maybe",
    }
    config_service._normalize_items(items)
    assert items["scene_memory_enabled"] == "0"
    assert items["prompt_dedup_enabled"] == "1"


def test_normalize_scene_memory_interval_snaps_to_recognition_multiple(config_service):
    items = {
        "normal_recognition_interval_sec": "5",
        "scene_memory_interval_sec": "7",
    }
    config_service._normalize_items(items)
    assert items["scene_memory_interval_sec"] == "10"


def test_normalize_scene_memory_interval_recenters_when_recognition_changes(config_service):
    config_service._config.set("scene_memory_interval_sec", "10")
    items = {"normal_recognition_interval_sec": "7"}
    config_service._normalize_items(items)
    assert items["normal_recognition_interval_sec"] == "7"
    assert items["scene_memory_interval_sec"] == "14"


def test_normalize_legacy_memory_mode_maps_to_new_flags(config_service):
    items = {"memory_mode": "scene_card"}
    config_service._normalize_items(items)
    assert items["scene_memory_enabled"] == "1"
    assert items["prompt_dedup_enabled"] == "1"
    assert "memory_mode" not in items


def test_normalize_danmu_speed_invalid_defaults(config_service):
    items = {"danmu_speed": "not-a-number"}
    config_service._normalize_items(items)
    assert items["danmu_speed"] == "2"


def test_normalize_floating_panel_speed_invalid_uses_default(config_service):
    items = {"floating_panel_speed": "bad"}
    config_service._normalize_items(items)
    from app.config_defaults import DEFAULT_FLOATING_PANEL_SPEED

    assert items["floating_panel_speed"] == DEFAULT_FLOATING_PANEL_SPEED


def test_apply_web_payload_masks_api_key_unchanged(config_service):
    config_service._config.set_api_key("real-secret-key")
    config_service.apply_web_payload({"api_key": MASKED_API_KEY, "danmu_speed": "2.5"})
    assert config_service._config.get_api_key() == "real-secret-key"
    assert config_service._config.get("danmu_speed") == "2.5"
