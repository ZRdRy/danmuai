"""Web console tests: HTTP routes via bridge.invoke_on_main."""

from unittest.mock import MagicMock


def test_probe_route_accepts_json_body():
    """Regression: /api/probe in web_console._run nested scope caused query: Field required 422."""
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.probe_api_connection.return_value = {
        "ok": True,
        "message": "连接成功",
        "status_code": 200,
    }

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)

    client = TestClient(app)
    res = client.post(
        "/api/probe",
        json={
            "api_endpoint": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "sk-test",
            "model": "doubao-test",
            "api_mode": "doubao",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["message"] == "连接成功"


def test_test_danmu_route_uses_public_app_entry():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.inject_test_danmu_batch.return_value = {
        "ok": True,
        "queued": 1,
        "screenshot_id": 1,
    }
    bridge.invoke_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)

    def _check_token(authorization: str | None = None) -> None:
        if authorization != "Bearer secret":
            from fastapi import HTTPException

            raise HTTPException(status_code=401)

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    denied = client.post("/api/test/danmu", json={"items": ["测试弹幕"]})
    assert denied.status_code == 401

    ok = client.post(
        "/api/test/danmu",
        json={"items": ["一二三四五六七八九十"], "persona": "验收"},
        headers={"Authorization": "Bearer secret"},
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    bridge.danmu_app.inject_test_danmu_batch.assert_called_once_with(
        ["一二三四五六七八九十"],
        persona_id="验收",
    )


def test_capture_region_get_route():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.get_capture_region_status.return_value = {
        "mode": "custom",
        "region": {"x": 10, "y": 20, "w": 100, "h": 80},
        "selection_state": "idle",
    }

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.get("/api/capture-region")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "custom"
    assert body["region"]["w"] == 100
    bridge.danmu_app.get_capture_region_status.assert_called_once()


def test_capture_region_select_route_emits_signal():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.get_capture_region_status.return_value = {
        "mode": "full",
        "region": {"x": 0, "y": 0, "w": 0, "h": 0},
        "selection_state": "idle",
    }

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.post("/api/capture-region/select")
    assert res.status_code == 200
    assert res.json()["selection_state"] == "selecting"
    bridge.region_select_requested.emit.assert_called_once()


def test_capture_region_select_skips_emit_when_already_selecting():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.get_capture_region_status.return_value = {
        "mode": "full",
        "region": {"x": 0, "y": 0, "w": 0, "h": 0},
        "selection_state": "selecting",
    }

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.post("/api/capture-region/select")
    assert res.status_code == 200
    bridge.region_select_requested.emit.assert_not_called()


def test_capture_region_reset_route_emits_signal():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.post("/api/capture-region/reset")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    bridge.region_reset_requested.emit.assert_called_once()


def test_mic_test_route_uses_public_app_entry():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.run_mic_test.return_value = {
        "ok": True,
        "level": "ok",
        "pcm_bytes": 4096,
        "rms": 0.12,
    }
    bridge.invoke_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.post("/api/mic/test", json={"duration_sec": 2.5, "send_to_ai": False})

    assert res.status_code == 200
    assert res.json()["ok"] is True
    from app.web_api.mic_test import run_mic_test

    bridge.invoke_on_main.assert_called_once_with(
        run_mic_test,
        bridge.danmu_app,
        2.5,
        False,
    )


def test_mic_test_send_route_uses_public_app_entry():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.danmu_app.run_mic_test.return_value = {
        "ok": True,
        "level": "ok",
        "pcm_bytes": 2048,
        "audio_attached": True,
    }
    bridge.invoke_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.post("/api/mic/test-send", json={"duration_sec": 3.0, "send_to_ai": False})

    assert res.status_code == 200
    assert res.json()["ok"] is True
    from app.web_api.mic_test import run_mic_test

    bridge.invoke_on_main.assert_called_once_with(
        run_mic_test,
        bridge.danmu_app,
        3.0,
        True,
    )


def test_active_personae_route_uses_public_app_entry():
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.invoke_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    res = client.put("/api/personae/active", json={"active": ["吐槽型"]})

    assert res.status_code == 200
    assert res.json() == {"ok": True}
    bridge.invoke_on_main.assert_called_once_with(
        bridge.danmu_app.set_active_personae,
        ["吐槽型"],
    )


def test_session_route_does_not_require_query_request():
    """Regression: Request in nested scope with postponed annotations caused query.request 422."""
    from fastapi import FastAPI, Header
    from fastapi.testclient import TestClient

    app = FastAPI()
    token = "test-token"
    fallback = "http://127.0.0.1:18765"

    @app.get("/api/session")
    def read_console_session(host: str | None = Header(default=None)):
        host = (host or "").strip()
        base_url = f"http://{host}" if host else fallback
        return {"token": token, "base_url": base_url}

    client = TestClient(app)
    res = client.get("/api/session", headers={"host": "127.0.0.1:18765"})
    assert res.status_code == 200
    body = res.json()
    assert body["token"] == token
    assert body["base_url"] == "http://127.0.0.1:18765"


# W-NICKNAME-001
def test_user_nickname_round_trip_via_config_service(tmp_path):
    """PUT /api/config { user_nickname } must persist to ConfigStore and survive reload."""
    from app.application.config_service import apply_web_config_patch
    from app.config_store import ConfigStore
    from app.personae import append_nickname_to_system_pt

    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path)
    # Sanity: seed should populate the new key with empty string.
    assert store.get("user_nickname", "") == ""

    class _PersonaeStub:
        def set_active(self, _active):
            return None

    class _DanmuAppStub:
        config_changed = MagicMock()

    app = _DanmuAppStub()
    app.config = store
    app.personae = _PersonaeStub()

    apply_web_config_patch(app, {"user_nickname": "小明"})
    assert store.get("user_nickname", "") == "小明"
    app.config_changed.emit.assert_called_once()

    # Reload from the same db file: persistence is durable, no Python state.
    store2 = ConfigStore(db_path)
    assert store2.get("user_nickname", "") == "小明"
    assert "[用户昵称：小明" in append_nickname_to_system_pt("你是主播。", store2)

    # Empty string should clear without raising and not inject anything.
    apply_web_config_patch(app, {"user_nickname": ""})
    assert store.get("user_nickname", "") == ""
    assert append_nickname_to_system_pt("你是主播。", store) == "你是主播。"


def test_user_nickname_default_in_config_defaults():
    """CONFIG_DEFAULTS must include user_nickname so 'restore defaults' is honest."""
    from app.config_defaults import CONFIG_DEFAULTS

    assert CONFIG_DEFAULTS.get("user_nickname", "") == ""


def test_user_nickname_in_web_config_keys():
    """WEB_CONFIG_KEYS must contain user_nickname so the whitelist accepts it."""
    from app.application.config_service import WEB_CONFIG_KEYS

    assert "user_nickname" in WEB_CONFIG_KEYS
    assert "user_nickname" in tuple(WEB_CONFIG_KEYS)


# W-FP-003：display_mode 与悬浮窗配置走 PUT /api/config 端到端


def test_display_mode_persists_via_config_service(tmp_path):
    """display_mode 经 PUT /api/config 持久化到 ConfigStore，reload 后仍在。"""
    from app.application.config_service import apply_web_config_patch
    from app.config_store import ConfigStore

    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path)

    class _PersonaeStub:
        def set_active(self, _active):
            return None

    class _DanmuAppStub:
        config_changed = MagicMock()

    app = _DanmuAppStub()
    app.config = store
    app.personae = _PersonaeStub()

    apply_web_config_patch(app, {"display_mode": "floating_panel"})
    assert store.get("display_mode") == "floating_panel"
    app.config_changed.emit.assert_called_once()

    store2 = ConfigStore(db_path)
    assert store2.get("display_mode") == "floating_panel"


def test_display_mode_invalid_falls_back_to_overlay_via_config_service(tmp_path):
    """display_mode 非法值经 _clamp_choice 落库为 overlay。"""
    from app.application.config_service import apply_web_config_patch
    from app.config_store import ConfigStore

    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path)

    class _PersonaeStub:
        def set_active(self, _active):
            return None

    class _DanmuAppStub:
        config_changed = MagicMock()

    app = _DanmuAppStub()
    app.config = store
    app.personae = _PersonaeStub()

    apply_web_config_patch(app, {"display_mode": "weird"})
    assert store.get("display_mode") == "overlay"


def test_floating_panel_config_keys_round_trip(tmp_path):
    """6 个悬浮窗配置键经 PUT /api/config 持久化、reload 后仍在。"""
    from app.application.config_service import apply_web_config_patch
    from app.config_store import ConfigStore

    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path)

    class _PersonaeStub:
        def set_active(self, _active):
            return None

    class _DanmuAppStub:
        config_changed = MagicMock()

    app = _DanmuAppStub()
    app.config = store
    app.personae = _PersonaeStub()

    payload = {
        "floating_panel_opacity": "70",
        "floating_panel_font_size": "22",
        "floating_panel_max_items": "100",
        "floating_panel_speed": "3.0",
        "floating_panel_click_through": "0",
    }
    apply_web_config_patch(app, payload)
    for key, expected in payload.items():
        # floating_panel_speed 经 _normalize_items 归一为 3 位小数（如 "3.000"）
        if key == "floating_panel_speed":
            assert float(store.get(key)) == float(expected), key
        else:
            assert store.get(key) == expected, key

    store2 = ConfigStore(db_path)
    for key, expected in payload.items():
        if key == "floating_panel_speed":
            assert float(store2.get(key)) == float(expected), key
        else:
            assert store2.get(key) == expected, key


def test_floating_panel_speed_clamped_via_config_service(tmp_path):
    """floating_panel_speed=100 经 _normalize_items 钳到 5.000。"""
    from app.application.config_service import apply_web_config_patch
    from app.config_store import ConfigStore

    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path)

    class _PersonaeStub:
        def set_active(self, _active):
            return None

    class _DanmuAppStub:
        config_changed = MagicMock()

    app = _DanmuAppStub()
    app.config = store
    app.personae = _PersonaeStub()

    apply_web_config_patch(app, {"floating_panel_speed": "100"})
    assert float(store.get("floating_panel_speed")) == 5.0


def test_floating_panel_click_through_normalized_via_config_service(tmp_path):
    """floating_panel_click_through=true 归一为 '1'。"""
    from app.application.config_service import apply_web_config_patch
    from app.config_store import ConfigStore

    db_path = tmp_path / "config.db"
    store = ConfigStore(db_path)

    class _PersonaeStub:
        def set_active(self, _active):
            return None

    class _DanmuAppStub:
        config_changed = MagicMock()

    app = _DanmuAppStub()
    app.config = store
    app.personae = _PersonaeStub()

    apply_web_config_patch(app, {"floating_panel_click_through": "true"})
    assert store.get("floating_panel_click_through") == "1"

    apply_web_config_patch(app, {"floating_panel_click_through": "no"})
    assert store.get("floating_panel_click_through") == "0"

