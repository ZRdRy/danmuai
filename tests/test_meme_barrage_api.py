"""烂梗公式化 Web API 与本地库测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.config_store import ConfigStore
from app.meme_barrage.store import MemeBarrageStore
from app.web_api import meme_barrage as meme_api


@pytest.fixture
def meme_app(tmp_path):
    config = ConfigStore(db_path=tmp_path / "meme_config.db")
    app = SimpleNamespace(
        config=config,
        config_changed=MagicMock(),
    )
    return app


def test_get_meta_defaults(meme_app):
    meta = meme_api.get_meta(meme_app)
    assert meta["enabled"] is False
    assert meta["category"] == "random"
    assert meta["display_mode"] == "full"
    assert meta["collect_batch_size"] == 2
    assert meta["display_batch_size"] == 2
    assert meta["library_count"] == 0
    assert meta["display_queue_size"] == 0


def test_save_settings_persists(meme_app):
    import json

    meme_api.save_settings(
        meme_app,
        {
            "enabled": True,
            "category": "tagged",
            "tag": "07",
            "display_mode": "ai",
            "collect_interval_sec": 8,
            "collect_batch_size": 30,
            "display_interval_sec": 6,
            "display_batch_size": 15,
        },
    )
    assert meme_app.config.get("meme_barrage_enabled") == "1"
    assert meme_app.config.get("meme_barrage_category") == "tagged"
    # 兼容旧单字符串 → 内部存为 JSON 数组
    assert json.loads(meme_app.config.get("meme_barrage_tag")) == ["07"]
    assert meme_app.config.get("meme_barrage_display_mode") == "ai"
    assert meme_app.config.get_int("meme_barrage_collect_interval_sec") == 8
    assert meme_app.config.get_int("meme_barrage_collect_batch_size") == 30
    meme_app.config_changed.emit.assert_called()


def test_save_settings_meta_reflects_input(meme_app):
    payload = {
        "enabled": True,
        "collect_interval_sec": 12,
        "collect_batch_size": 15,
    }
    meta = meme_api.save_settings(meme_app, payload)
    assert meta["collect_interval_sec"] == 12
    assert meta["collect_batch_size"] == 15
    stored = meme_api.get_meta(meme_app)
    assert stored["collect_interval_sec"] == 12
    assert stored["collect_batch_size"] == 15


def test_store_insert_and_clear(meme_app):
    store = MemeBarrageStore(meme_app.config)
    added = store.insert_many([("句A", "06", 1), ("句B", "06", 2), ("句A", "06", 3)])
    assert added == 2
    assert store.count() == 2
    store.clear()
    assert store.count() == 0


def test_get_tags_fallback(monkeypatch):
    monkeypatch.setattr(
        meme_api.MemeBarrageApiClient,
        "dict_list",
        lambda self: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    meme_api._tags_cache = None
    resp = meme_api.get_tags()
    assert len(resp["tags"]) == 27


def test_meme_barrage_routes_registered(tmp_path):
    from app.web_api.routes import register_web_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    bridge = MagicMock()
    bridge.invoke_on_main.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
    config = ConfigStore(db_path=tmp_path / "meme_routes.db")
    bridge.danmu_app = SimpleNamespace(
        config=config,
        config_changed=MagicMock(),
    )

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    client = TestClient(app)

    meta = client.get("/api/meme-barrage/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["library_count"] == 0
    assert body["enabled"] is False
    assert body["category"] == "random"
    assert body["display_mode"] == "full"
    assert "collect_interval_sec" in body
    assert "display_interval_sec" in body

    tags = client.get("/api/meme-barrage/tags")
    assert tags.status_code == 200
    assert len(tags.json()["tags"]) >= 1

    settings = client.put(
        "/api/meme-barrage/settings",
        json={"enabled": True, "category": "random"},
    )
    assert settings.status_code == 200
    assert settings.json()["enabled"] is True

    cleared = client.post("/api/meme-barrage/clear")
    assert cleared.status_code == 200
    assert cleared.json()["library_count"] == 0


def test_format_tags_for_remote_api_caps_multi_select():
    from app.meme_barrage.client import format_tags_for_remote_api

    tags = ["00", "01", "02", "03", "05", "15"]
    assert format_tags_for_remote_api(tags, 1) == "00,01,02"


def test_save_settings_caps_tag_list(meme_app):
    meme_api.save_settings(
        meme_app,
        {"tag": ["00", "01", "02", "03", "05"]},
    )
    import json

    assert json.loads(meme_app.config.get("meme_barrage_tag")) == ["00", "01", "02"]


def test_get_meta_after_config_close_returns_zero_counts(meme_app):
    """W-QUIT-TEARDOWN-001：退出竞态下 closed DB 不得 500。"""
    store = MemeBarrageStore(meme_app.config)
    store.insert_many([("句A", "06", 1)])
    assert meme_api.get_meta(meme_app)["library_count"] == 1
    meme_app.config.close()
    meta = meme_api.get_meta(meme_app)
    assert meta["library_count"] == 0
    assert meta["display_queue_size"] == 0


def test_format_tags_for_remote_api_small_selection():
    from app.meme_barrage.client import format_tags_for_remote_api

    assert format_tags_for_remote_api(["06", "07"], 1) == "06,07"
    assert format_tags_for_remote_api(["06"], 5) == "06"
    assert format_tags_for_remote_api([], 1) == "06"
