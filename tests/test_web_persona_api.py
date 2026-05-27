"""Persona web API service tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.config_store import ConfigStore
from app.personae import BUILTIN_PERSONAE, PersonaManager
from app.templates import TemplateManager
from app.web_api import persona as persona_api


@pytest.fixture
def persona_app(tmp_path):
    db = tmp_path / "config.db"
    config = ConfigStore(db_path=db)
    config.set("danmu_display_mode", "realtime")
    personae = PersonaManager(config)
    templates = TemplateManager(config)
    app = SimpleNamespace(
        config=config,
        personae=personae,
        templates=templates,
        config_changed=MagicMock(),
    )
    return app


def test_create_and_save_custom_persona(persona_app):
    created = persona_api.create_persona(persona_app, "测试人格A")
    assert created["id"] == "测试人格A"

    persona_api.save_template(
        persona_app,
        "测试人格A",
        "风格轻松",
        "请生成弹幕：",
    )
    detail = persona_api.get_template_detail(persona_app, "测试人格A")
    assert "风格轻松" in detail["system_custom"]
    assert not detail["builtin"]
    assert detail["system_editable"]

    system_pt, user_pt = persona_app.personae.get_prompt("测试人格A")
    assert "风格轻松" in system_pt
    assert user_pt == "请生成弹幕："

    versions = persona_api.list_versions(persona_app, "测试人格A")
    assert len(versions) >= 1


def test_list_dedupes_builtin_with_custom_override(persona_app):
    persona_api.save_template(persona_app, "搞笑玩梗型", "覆盖风格", "用户提示")
    persona_api.save_template(persona_app, "专业分析型", "覆盖风格2", "用户提示2")
    names = persona_app.personae.list()
    assert names.count("搞笑玩梗型") == 1
    assert names.count("专业分析型") == 1


def test_builtin_save_system_and_user_prompt(persona_app):
    persona_api.save_template(persona_app, "吐槽型", "多用网络热梗", "自定义用户提示")
    detail = persona_api.get_template_detail(persona_app, "吐槽型")
    assert detail["builtin"]
    assert detail["system_editable"]
    assert detail["user_pt"] == "自定义用户提示"
    assert "多用网络热梗" in detail["system_custom"]

    system_pt, user_pt = persona_app.personae.get_prompt("吐槽型")
    assert "多用网络热梗" in system_pt
    assert user_pt == "自定义用户提示"


def test_builtin_restore_clears_saved_override(persona_app):
    persona_api.save_template(persona_app, "吐槽型", "临时覆盖", "自定义用户提示")
    restored = persona_api.restore_builtin_default(persona_app, "吐槽型")
    assert "吐槽感更强" in restored["system_custom"]
    detail = persona_api.get_template_detail(persona_app, "吐槽型")
    assert "吐槽感更强" in detail["system_custom"]
    assert "临时覆盖" not in detail["system_custom"]


def test_reply_contract_follows_normal_reply_count(persona_app):
    persona_app.config.set("normal_reply_count", "9")
    detail = persona_api.get_template_detail(persona_app, "吐槽型")
    contract = detail["reply_contract"]
    assert "固定返回 9 条弹幕" in contract
    assert "必须与当前画面或直播氛围相关" in contract
    assert "前 4 条必须强相关当前画面" not in contract


def test_reply_contract_follows_danmu_max_chars(persona_app):
    persona_app.config.set("danmu_max_chars", "28")
    detail = persona_api.get_template_detail(persona_app, "吐槽型")
    assert "每条不超过 28 个字" in detail["reply_contract"]


def test_builtin_system_custom_differs_by_persona(persona_app):
    a = persona_api.get_template_detail(persona_app, "吐槽型")["system_custom"]
    b = persona_api.get_template_detail(persona_app, "文艺型")["system_custom"]
    assert a and b and a != b


def test_delete_custom_persona(persona_app):
    persona_api.create_persona(persona_app, "待删人格")
    persona_api.delete_persona(persona_app, "待删人格")
    with pytest.raises(ValueError):
        persona_api.get_template_detail(persona_app, "待删人格")


_NEW_STYLE_PERSONAE = (
    "傲娇型",
    "腹黑型",
    "中二型",
    "治愈型",
    "毒舌型",
    "元气型",
    "社恐型",
)


def test_new_style_builtin_personae(persona_app):
    for name in _NEW_STYLE_PERSONAE:
        assert name in BUILTIN_PERSONAE
        detail = persona_api.get_template_detail(persona_app, name)
        assert detail["builtin"]
        assert detail["system_custom"]
        system_pt, user_pt = persona_app.personae.get_prompt(name)
        assert system_pt
        assert user_pt
