"""人格/模板 Web 逻辑；由 routes 调用，写配置经 DanmuApp/ConfigStore 既有入口。

路由（由 ``app.web_api.routes`` 注册）：
- ``GET /api/personae``：列出内置 + 自定义人格清单。
- ``GET /api/personae/{name}``：返回 ``system_pt`` + ``user_pt``（中文/英文按当前语言）。
- ``POST/PUT /api/personae``：写入自定义人格；落 ``custom_personae`` JSON 字符串。
- ``DELETE /api/personae/{name}``：删除自定义人格；同步从 ``active_personae`` 剔除。

与 ``PersonaManager`` 的关系：本模块只做 Web 入参与出参转换，业务逻辑全部委托
``app.personae.PersonaManager``；不直接读写 ConfigStore 内部字段。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.personae import (
    BUILTIN_PERSONAE,
    PersonaManager,
    default_user_prompt,
    ensure_reply_contract,
    get_reply_contract,
    strip_reply_contract,
)
from app.templates import TemplateManager
from app.translations import Translator

if TYPE_CHECKING:
    from main import DanmuApp


def get_template_detail(app: "DanmuApp", name: str) -> dict[str, Any]:
    personae: PersonaManager = app.personae
    templates: TemplateManager = app.templates

    from app.personae import normalize_persona_name, persona_display_name

    name = normalize_persona_name(name)
    if name not in personae.list():
        raise ValueError("人格不存在")

    is_builtin = name in BUILTIN_PERSONAE

    system_pt, user_pt = personae.get_prompt(name)
    if not system_pt:
        system_pt, user_pt = templates.load(name)

    return {
        "id": name,
        "label": persona_display_name(name),
        "builtin": is_builtin,
        "editable": not is_builtin,
        "system_editable": True,
        "can_save": True,
        "system_custom": strip_reply_contract(system_pt),
        "user_pt": user_pt or default_user_prompt(),
        "reply_contract": get_reply_contract(app.config),
    }


def list_versions(app: "DanmuApp", name: str) -> list[dict[str, Any]]:
    from app.persona_version_history import list_versions as list_persona_versions
    from app.personae import normalize_persona_name

    name = normalize_persona_name(name)
    return list_persona_versions(app.templates, name)


def save_template(app: "DanmuApp", name: str, system_custom: str, user_pt: str) -> None:
    from app.personae import normalize_persona_name

    name = normalize_persona_name(name)
    reply_contract = get_reply_contract(app.config)

    _, existing_user = app.templates.load(name)
    if not (user_pt or "").strip():
        user_pt = existing_user or default_user_prompt()

    custom = (system_custom or "").strip()
    if custom:
        full_system = f"{reply_contract} {custom}".strip()
    elif name in BUILTIN_PERSONAE:
        prompt = BUILTIN_PERSONAE[name]
        if Translator.get_language() == "en":
            base = prompt["system_en"]
        else:
            base = prompt["system_zh"]
        full_system = ensure_reply_contract(base, app.config)
    else:
        full_system = reply_contract

    app.personae.save_custom(name, full_system, user_pt)
    app.templates.save(name, full_system, user_pt)
    app.config_changed.emit()


def rollback_preview(app: "DanmuApp", name: str, version: int) -> dict[str, Any]:
    from app.personae import normalize_persona_name

    name = normalize_persona_name(name)
    system_pt, user_pt = app.templates.load(name, version)
    return {
        "system_custom": strip_reply_contract(system_pt),
        "user_pt": user_pt or default_user_prompt(),
        "version": version,
    }


def create_persona(app: "DanmuApp", name: str) -> dict[str, Any]:
    from app.personae import normalize_persona_name, persona_display_name, validate_persona_name

    name = normalize_persona_name(validate_persona_name(name))
    if name in app.personae.list():
        raise ValueError("人格名称已存在")

    contract = get_reply_contract(app.config)
    user_pt = default_user_prompt()
    app.personae.save_custom(name, contract, user_pt)
    app.templates.save(name, contract, user_pt)
    app.config_changed.emit()
    return {"id": name, "label": persona_display_name(name)}


def delete_persona(app: "DanmuApp", name: str) -> None:
    from app.personae import normalize_persona_name

    name = normalize_persona_name(name)
    if name in BUILTIN_PERSONAE:
        raise ValueError("内置人格不可删除")
    app.personae.delete_custom(name)
    app.config_changed.emit()


def restore_builtin_default(app: "DanmuApp", name: str) -> dict[str, Any]:
    from app.personae import normalize_persona_name

    name = normalize_persona_name(name)
    if name not in BUILTIN_PERSONAE:
        raise ValueError("仅内置人格可恢复默认")

    app.personae.delete_custom(name)
    app.config_changed.emit()
    prompt = BUILTIN_PERSONAE[name]
    if Translator.get_language() == "en":
        system_custom = prompt["system_en"]
        user_pt = prompt["user_en"]
    else:
        system_custom = prompt["system_zh"]
        user_pt = prompt["user_zh"]
    return {
        "system_custom": system_custom,
        "user_pt": user_pt,
    }
