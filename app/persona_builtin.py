"""Built-in persona definitions loaded from data/personae_builtin.json."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from app.bundle_paths import resource_path

_BUILTIN_PATH = resource_path("data") / "personae_builtin.json"


@lru_cache(maxsize=1)
def _load_builtin_payload() -> dict:
    raw = _BUILTIN_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("personae_builtin.json must be a JSON object")
    return payload


def _personae_dict() -> dict:
    personae = _load_builtin_payload().get("personae", {})
    if not isinstance(personae, dict):
        raise ValueError("personae_builtin.json: personae must be an object")
    return personae


BUILTIN_PERSONAE: dict = _personae_dict()

_payload = _load_builtin_payload()
BUILTIN_PERSONA_PINNED_FIRST: tuple[str, ...] = tuple(_payload.get("pinned_first", ()))
LEGACY_NAME_MAP: dict[str, str] = dict(_payload.get("legacy_name_map", {}))
PERSONA_NAME_KEYS: dict[str, str] = dict(_payload.get("persona_name_keys", {}))


def builtin_personae_names() -> list[str]:
    pinned = [n for n in BUILTIN_PERSONA_PINNED_FIRST if n in BUILTIN_PERSONAE]
    rest = [n for n in BUILTIN_PERSONAE if n not in pinned]
    return pinned + rest


def normalize_persona_name(name: str) -> str:
    if not name:
        return ""
    return LEGACY_NAME_MAP.get(name, name)


_PERSONA_NAME_INVALID_CHARS_RE = re.compile(r"[/\\%#?]")


def validate_persona_name(name: str) -> str:
    """校验新建人格名称；含 URL 路径保留字符时无法通过 /api/personae/{name} 访问。"""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("请输入人格名称")
    if _PERSONA_NAME_INVALID_CHARS_RE.search(cleaned):
        raise ValueError("人格名称不能包含 / \\ % # ? 等特殊字符")
    return cleaned
