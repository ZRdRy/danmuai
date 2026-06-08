"""烂梗库标签多选（multi-select）的数据契约测试。

覆盖：
- PUT 保存 array / empty / null 时的写库格式
- 旧值（单字符串 / 逗号字符串 / 已迁移 JSON 数组）的读取兼容
- Pydantic payload 接受 list[str] 与 str（向后兼容）
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.config_store import ConfigStore
from app.meme_barrage.config import read_meme_barrage_settings
from app.web_api import meme_barrage as meme_api


@pytest.fixture
def meme_app(tmp_path):
    config = ConfigStore(db_path=tmp_path / "meme_multi_tag.db")
    app = SimpleNamespace(
        config=config,
        config_changed=MagicMock(),
    )
    return app


# ---------------------------------------------------------------------------
# save_settings → 写入 JSON 数组
# ---------------------------------------------------------------------------


def test_save_settings_tag_array(meme_app):
    meme_api.save_settings(meme_app, {"tag": ["06", "07"]})
    raw = meme_app.config.get("meme_barrage_tag")
    assert json.loads(raw) == ["06", "07"]


def test_save_settings_tag_empty(meme_app):
    meme_api.save_settings(meme_app, {"tag": []})
    raw = meme_app.config.get("meme_barrage_tag")
    # 空数组兜底到 ["06"]
    assert json.loads(raw) == ["06"]


def test_save_settings_tag_null(meme_app):
    meme_app.config.set("meme_barrage_tag", "07")  # 已有旧值
    meme_api.save_settings(meme_app, {"tag": None})
    raw = meme_app.config.get("meme_barrage_tag")
    assert json.loads(raw) == ["06"]


def test_save_settings_tag_single_string_legacy(meme_app):
    """旧单字符串应被解析为单元素数组写入。"""
    meme_api.save_settings(meme_app, {"tag": "07"})
    raw = meme_app.config.get("meme_barrage_tag")
    assert json.loads(raw) == ["07"]


def test_save_settings_tag_comma_string_legacy(meme_app):
    """旧逗号分隔字符串应被切分为数组写入。"""
    meme_api.save_settings(meme_app, {"tag": "06,07,08"})
    raw = meme_app.config.get("meme_barrage_tag")
    assert json.loads(raw) == ["06", "07", "08"]


# ---------------------------------------------------------------------------
# read_meme_barrage_settings → 向后兼容读取
# ---------------------------------------------------------------------------


def test_read_settings_legacy_string(meme_app):
    """单字符串 ``"06,07"`` 也能被读为 list。"""
    meme_app.config.set("meme_barrage_tag", "06,07")
    settings = read_meme_barrage_settings(meme_app.config)
    assert settings["tag"] == ["06", "07"]


def test_read_settings_legacy_single(meme_app):
    """旧单字符串 ``"06"`` 也能被读为 list。"""
    meme_app.config.set("meme_barrage_tag", "06")
    settings = read_meme_barrage_settings(meme_app.config)
    assert settings["tag"] == ["06"]


def test_read_settings_json_array(meme_app):
    """新格式（JSON 数组）原样读取。"""
    meme_app.config.set("meme_barrage_tag", json.dumps(["06", "07"]))
    settings = read_meme_barrage_settings(meme_app.config)
    assert settings["tag"] == ["06", "07"]


def test_read_settings_empty_falls_back(meme_app):
    """空字符串 / 空白 / 空 list 都应回退到默认 ["06"]。"""
    for raw in ("", "   ", "[]"):
        meme_app.config.set("meme_barrage_tag", raw)
        settings = read_meme_barrage_settings(meme_app.config)
        assert settings["tag"] == ["06"], f"raw={raw!r}"


def test_read_settings_default_when_missing(meme_app):
    """键不存在时回退默认 ["06"]。"""
    # 不显式设置 meme_barrage_tag
    settings = read_meme_barrage_settings(meme_app.config)
    assert settings["tag"] == ["06"]


def test_read_settings_caps_at_three_tags(meme_app):
    """超过 3 个标签时读取应截断为前 3 个。"""
    meme_app.config.set(
        "meme_barrage_tag",
        json.dumps(["00", "01", "02", "03", "05", "15"]),
    )
    settings = read_meme_barrage_settings(meme_app.config)
    assert settings["tag"] == ["00", "01", "02"]


# ---------------------------------------------------------------------------
# Pydantic 负载模型（routes.py 闭包内 MemeBarrageSettingsPayload）：
# list[str] | None，拒绝 list[非 str]，端到端 PUT 走 TestClient
# ---------------------------------------------------------------------------


def _build_test_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.web_api.routes import register_web_routes

    app = FastAPI()
    bridge = MagicMock()
    bridge.invoke_on_main.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
    config = ConfigStore(db_path=__import__("pathlib").Path(__file__).parent / ".meme_pydantic_test.db")
    bridge.danmu_app = SimpleNamespace(
        config=config,
        config_changed=MagicMock(),
    )

    def _check_token(_authorization: str | None = None) -> None:
        return None

    register_web_routes(app, bridge, _check_token)
    return app, TestClient(app)


def test_pydantic_accepts_list_via_put(tmp_path):
    """PUT ``tag: ["06", "07"]`` 应被 Pydantic 接受并落库为 JSON 数组。"""
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.config_store import ConfigStore
    from app.web_api.routes import register_web_routes

    db = tmp_path / "meme_pyd.db"
    config = ConfigStore(db_path=db)
    app = FastAPI()
    bridge = MagicMock()
    bridge.invoke_on_main.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
    bridge.danmu_app = SimpleNamespace(config=config, config_changed=MagicMock())
    register_web_routes(app, bridge, lambda *_a, **_kw: None)
    client = TestClient(app)

    resp = client.put(
        "/api/meme-barrage/settings",
        json={"enabled": True, "category": "tagged", "tag": ["06", "07"]},
    )
    assert resp.status_code == 200
    assert json.loads(config.get("meme_barrage_tag")) == ["06", "07"]


def test_pydantic_accepts_empty_list_via_put(tmp_path):
    """PUT ``tag: []`` 应被接受；落库时由 save 层兜底为 ``["06"]``。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.config_store import ConfigStore
    from app.web_api.routes import register_web_routes

    db = tmp_path / "meme_pyd_empty.db"
    config = ConfigStore(db_path=db)
    app = FastAPI()
    bridge = MagicMock()
    bridge.invoke_on_main.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
    bridge.danmu_app = SimpleNamespace(config=config, config_changed=MagicMock())
    register_web_routes(app, bridge, lambda *_a, **_kw: None)
    client = TestClient(app)

    resp = client.put(
        "/api/meme-barrage/settings",
        json={"tag": []},
    )
    assert resp.status_code == 200
    assert json.loads(config.get("meme_barrage_tag")) == ["06"]


def test_pydantic_rejects_non_string_list(tmp_path):
    """PUT ``tag: [123]``（非 str list）应被 Pydantic 422 拒绝。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.config_store import ConfigStore
    from app.web_api.routes import register_web_routes

    db = tmp_path / "meme_pyd_reject.db"
    config = ConfigStore(db_path=db)
    app = FastAPI()
    bridge = MagicMock()
    bridge.invoke_on_main.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
    bridge.danmu_app = SimpleNamespace(config=config, config_changed=MagicMock())
    register_web_routes(app, bridge, lambda *_a, **_kw: None)
    client = TestClient(app)

    resp = client.put(
        "/api/meme-barrage/settings",
        json={"tag": [123]},
    )
    assert resp.status_code == 422


def test_save_settings_accepts_legacy_str_via_payload(meme_app):
    """端到端：旧单字符串 payload 在 save 层被规整为 list。"""
    meme_api.save_settings(meme_app, {"tag": "06"})
    raw = meme_app.config.get("meme_barrage_tag")
    assert json.loads(raw) == ["06"]
