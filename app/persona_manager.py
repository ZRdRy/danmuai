from __future__ import annotations

import json
import random

from app.config_store import ConfigStore
from app.persona_builtin import (
    BUILTIN_PERSONAE,
    builtin_personae_names,
    normalize_persona_name,
)
from app.persona_contract import ensure_reply_contract
from app.translations import tr

_REMOVED_PERSONAE = frozenset({"阿静", "测试"})


class PersonaManager:
    DEFAULT_ACTIVE = ["路人惊讶型", "搞笑玩梗型", "专业分析型", "捧场活跃型", "轻度吐槽型"]
    _ACTIVE_VERSION = 3

    def __init__(self, config: ConfigStore):
        self.config = config
        self._custom: dict = {}
        self._migrate_active_personae()
        self._purge_removed_personae()

    def _migrate_active_personae(self):
        version = self.config.get_int("active_personae_version", 0)
        if version < self._ACTIVE_VERSION:
            if version < 2:
                self.config.set_json("active_personae", self.DEFAULT_ACTIVE)
            else:
                active = self.config.get_json("active_personae", self.DEFAULT_ACTIVE)
                filtered = self._filter_removed_active(active)
                self.config.set_json("active_personae", filtered)
            self.config.set("active_personae_version", str(self._ACTIVE_VERSION))

    def _filter_removed_active(self, names: list[str]) -> list[str]:
        filtered = [
            normalize_persona_name(name)
            for name in names
            if name and normalize_persona_name(name) not in _REMOVED_PERSONAE
        ]
        return filtered or list(self.DEFAULT_ACTIVE)

    def _filter_pickable_active(self, names: list[str]) -> list[str]:
        valid = set(self.list())
        return [
            normalize_persona_name(name)
            for name in names
            if name and normalize_persona_name(name) in valid
        ]

    def _purge_removed_personae(self):
        active = self.config.get_json("active_personae", None)
        if isinstance(active, list):
            filtered = self._filter_removed_active(active)
            if filtered != active:
                self.config.set_json("active_personae", filtered)

        custom = self._load_custom()
        removed = [name for name in custom if name in _REMOVED_PERSONAE]
        if removed:
            for name in removed:
                custom.pop(name, None)
            self._custom = custom
            self.config.set("custom_personae", json.dumps(custom, ensure_ascii=False))

    def list(self) -> list[str]:
        builtin_set = set(BUILTIN_PERSONAE.keys())
        custom = [name for name in self._load_custom_names() if name not in builtin_set]
        return builtin_personae_names() + custom

    def get_prompt(self, name: str) -> tuple[str, str]:
        from app.translations import Translator

        normalized = normalize_persona_name(name)
        custom = self._load_custom()
        if normalized in custom:
            prompt = custom[normalized]
            system_pt = (prompt.get("system_pt") or "").strip()
            if system_pt:
                user_pt = prompt.get("user_pt") or tr("template.default_user_prompt")
                return ensure_reply_contract(system_pt, self.config), user_pt

        if normalized in BUILTIN_PERSONAE:
            prompt = BUILTIN_PERSONAE[normalized]
            if Translator.get_language() == "en":
                return ensure_reply_contract(prompt["system_en"], self.config), prompt["user_en"]
            return ensure_reply_contract(prompt["system_zh"], self.config), prompt["user_zh"]
        return "", ""

    def get_active(self) -> list[str]:
        names = self.config.get_json("active_personae", self.DEFAULT_ACTIVE)
        normalized = self._filter_removed_active(names if isinstance(names, list) else [])
        pickable = self._filter_pickable_active(normalized)
        return pickable or list(self.DEFAULT_ACTIVE)

    def set_active(self, names: list[str]):
        normalized = self._filter_removed_active([normalize_persona_name(name) for name in names if name])
        self.config.set_json("active_personae", normalized)

    def _load_custom_names(self) -> list[str]:
        return list(self._load_custom().keys())

    def _load_custom(self) -> dict:
        if not self._custom:
            raw = self.config.get("custom_personae", "{}")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                self._custom = {normalize_persona_name(name): value for name, value in loaded.items()}
            else:
                self._custom = {}
        return self._custom

    def save_custom(self, name: str, system_pt: str, user_pt: str):
        custom = self._load_custom()
        custom[normalize_persona_name(name)] = {"system_pt": system_pt, "user_pt": user_pt}
        self._custom = custom
        self.config.set("custom_personae", json.dumps(custom, ensure_ascii=False))

    def delete_custom(self, name: str):
        norm = normalize_persona_name(name)
        custom = self._load_custom()
        custom.pop(norm, None)
        self._custom = custom
        self.config.set("custom_personae", json.dumps(custom, ensure_ascii=False))

        raw = self.config.get_json("active_personae", None)
        if isinstance(raw, list):
            pruned = [n for n in raw if n and normalize_persona_name(n) != norm]
            if len(pruned) != len(raw):
                self.set_active(pruned)

    def pick_random(self) -> str:
        active = self.get_active()
        return random.choice(active) if active else self.DEFAULT_ACTIVE[0]
