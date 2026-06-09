"""W-TEST-COVER-001: PUT /api/config full WEB_CONFIG_KEYS payload round-trip."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.application.config_service import WEB_CONFIG_KEYS, apply_web_config_patch
from app.config_store import ConfigStore

from tests.helpers.config_payload import (
    boundary_web_config_overrides,
    expected_normalized_web_config,
    full_web_config_payload,
    make_config_app_stub,
)


def test_full_web_config_payload_round_trip_via_config_service(tmp_path):
    """All WEB_CONFIG_KEYS in one patch normalize, persist, and survive reload."""
    db_path = tmp_path / "full_payload.db"
    store = ConfigStore(db_path)
    app = make_config_app_stub(store)

    payload = full_web_config_payload(**boundary_web_config_overrides())
    assert set(payload.keys()) == set(WEB_CONFIG_KEYS)

    expected = expected_normalized_web_config(store, payload)
    apply_web_config_patch(app, payload)

    app.config_changed.emit.assert_called_once()

    for key in WEB_CONFIG_KEYS:
        assert store.get(key) == expected[key], key

    store2 = ConfigStore(db_path)
    for key in WEB_CONFIG_KEYS:
        assert store2.get(key) == expected[key], f"reload:{key}"
    store2.close()


def test_full_web_config_payload_via_save_config_bridge(workspace_tmp, qapp):
    """save_config_via_bridge path used by PUT /api/config (main-thread apply)."""
    del qapp
    from app.web_console import WebConsoleBridge, save_config_via_bridge

    db_path = workspace_tmp / "bridge_full.db"
    store = ConfigStore(db_path)
    app_stub = make_config_app_stub(store)

    danmu_app = MagicMock()
    danmu_app.config = store
    danmu_app.personae = app_stub.personae
    danmu_app.config_changed = app_stub.config_changed
    danmu_app.apply_web_config_payload = lambda payload: apply_web_config_patch(danmu_app, payload)

    bridge = WebConsoleBridge(danmu_app)
    payload = full_web_config_payload(**boundary_web_config_overrides())
    expected = expected_normalized_web_config(store, payload)

    result = save_config_via_bridge(bridge, payload)
    assert result == {"ok": True}

    for key in WEB_CONFIG_KEYS:
        assert store.get(key) == expected[key], key


def test_danmu_speed_zero_clamps_to_min(tmp_path):
    """Explicit §三-8 regression: danmu_speed=0 must not freeze scrolling."""
    store = ConfigStore(tmp_path / "speed_zero.db")
    app = make_config_app_stub(store)
    apply_web_config_patch(app, {"danmu_speed": "0"})
    assert store.get("danmu_speed") == "0.5"
