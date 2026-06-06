"""Persona management entry point; re-exports split modules for backward compatibility."""

from __future__ import annotations

from app.persona_builtin import (
    BUILTIN_PERSONA_PINNED_FIRST,
    BUILTIN_PERSONAE,
    LEGACY_NAME_MAP,
    PERSONA_NAME_KEYS,
    normalize_persona_name,
    validate_persona_name,
)
from app.persona_contract import (
    DEFAULT_NORMAL_REPLY_COUNT,
    DEFAULT_REPLY_FILLER_COUNT,
    DEFAULT_REPLY_SCENE_COUNT,
    LIVE_TOPIC_MAX_LEN,
    NICKNAME_MAX_LEN,
    NORMAL_REPLY_COUNT_MAX,
    NORMAL_REPLY_COUNT_MIN,
    REPLY_CONTRACT,
    REPLY_CONTRACT_ALIASES,
    REPLY_CONTRACT_EN,
    REPLY_CONTRACT_ZH,
    REPLY_COUNT_MAX,
    REPLY_COUNT_MIN,
    append_live_topic_to_system_pt,
    append_nickname_to_system_pt,
    build_normal_reply_contract_en,
    build_normal_reply_contract_zh,
    build_reply_contract_en,
    build_reply_contract_zh,
    ensure_reply_contract,
    get_reply_contract,
    normal_reply_count_from_config,
    reply_counts_from_config,
    strip_reply_contract,
)
from app.persona_manager import PersonaManager
from app.translations import tr


def persona_display_name(name: str) -> str:
    normalized = normalize_persona_name(name)
    key = PERSONA_NAME_KEYS.get(normalized)
    return tr(key) if key else normalized


def default_user_prompt() -> str:
    return tr("template.default_user_prompt")


__all__ = [
    "BUILTIN_PERSONAE",
    "BUILTIN_PERSONA_PINNED_FIRST",
    "DEFAULT_NORMAL_REPLY_COUNT",
    "DEFAULT_REPLY_FILLER_COUNT",
    "DEFAULT_REPLY_SCENE_COUNT",
    "LEGACY_NAME_MAP",
    "NORMAL_REPLY_COUNT_MAX",
    "NORMAL_REPLY_COUNT_MIN",
    "PERSONA_NAME_KEYS",
    "PersonaManager",
    "REPLY_CONTRACT",
    "REPLY_CONTRACT_ALIASES",
    "REPLY_CONTRACT_EN",
    "REPLY_CONTRACT_ZH",
    "REPLY_COUNT_MAX",
    "REPLY_COUNT_MIN",
    "build_normal_reply_contract_en",
    "build_normal_reply_contract_zh",
    "build_reply_contract_en",
    "build_reply_contract_zh",
    "default_user_prompt",
    "ensure_reply_contract",
    "get_reply_contract",
    "normal_reply_count_from_config",
    "normalize_persona_name",
    "validate_persona_name",
    "persona_display_name",
    "reply_counts_from_config",
    "strip_reply_contract",
    "LIVE_TOPIC_MAX_LEN",
    "NICKNAME_MAX_LEN",
    "append_live_topic_to_system_pt",
    "append_nickname_to_system_pt",
]
