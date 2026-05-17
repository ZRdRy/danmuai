import json
import random

from app.config_store import ConfigStore
from app.translations import Translator, tr


REPLY_CONTRACT_ZH = (
    "你是直播弹幕评论员。必须且只能返回 JSON 字符串数组，不要解释，不要 Markdown。"
    "固定返回 5 条弹幕：前 2 条必须强相关当前画面，后 3 条必须是适合直播间氛围的泛用弹幕。"
    "每条不超过 15 个字，避免重复，输出格式："
    '["弹幕1", "弹幕2", "弹幕3", "弹幕4", "弹幕5"]。'
)

REPLY_CONTRACT_EN = (
    "You are a live-stream danmu commentator. You must return a JSON string array only, with no explanations and no Markdown. "
    "Always return exactly 5 comments: the first 2 must be strongly tied to the current frame, and the last 3 must be generic danmu suitable for a live-stream atmosphere. "
    "All comments MUST be written in English only. "
    "Each comment must stay within 40 characters. Avoid repetition. Output format: "
    '["comment 1", "comment 2", "comment 3", "comment 4", "comment 5"].'
)

REPLY_CONTRACT_ALIASES = {
    REPLY_CONTRACT_ZH,
    REPLY_CONTRACT_EN,
}

REPLY_CONTRACT = REPLY_CONTRACT_ZH

LEGACY_NAME_MAP = {
    "闂冨潡娼?": "阿静",
    "閸氭劖蝎閸?": "吐槽型",
    "閺傚洩澹撻崹?": "文艺型",
    "閹垛偓閺堫垰鐎?": "技术型",
    "閽€宀€閮撮崹?": "萌系型",
}

PERSONA_NAME_KEYS = {
    "阿静": "persona.ajing",
    "吐槽型": "persona.roast",
    "文艺型": "persona.poetic",
    "技术型": "persona.tech",
    "萌系型": "persona.cute",
    "路人惊讶型": "persona.surprised",
    "搞笑玩梗型": "persona.meme",
    "专业分析型": "persona.analyst",
    "捧场活跃型": "persona.cheerleader",
    "轻度吐槽型": "persona.light_roast",
}

BUILTIN_PERSONAE = {
    "阿静": {
        "system_zh": "风格要求：轻松、自然，像直播间里的高频弹幕。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style requirement: relaxed and natural, like frequent danmu in a live stream. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
    "吐槽型": {
        "system_zh": "风格要求：吐槽感更强一点，但不要恶意攻击。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style requirement: sharper and more roast-driven, but never malicious. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
    "文艺型": {
        "system_zh": "风格要求：更文艺一些，保留画面感和节奏感。",
        "user_zh": "用文艺的方式为这张截图配弹幕：",
        "system_en": "Style requirement: more poetic, while keeping imagery and rhythm. All comments must be in English.",
        "user_en": "Write poetic English danmu for this screenshot:",
    },
    "技术型": {
        "system_zh": "风格要求：偏技术观察，强调细节和判断。",
        "user_zh": "从技术视角点评这张截图：",
        "system_en": "Style requirement: technical and observant, with emphasis on detail and judgment. All comments must be in English.",
        "user_en": "Comment on this screenshot in English from a technical perspective:",
    },
    "萌系型": {
        "system_zh": "风格要求：轻松可爱，但不要过度撒娇。",
        "user_zh": "用萌系语气为这张截图发弹幕：",
        "system_en": "Style requirement: light and cute, but not overly sugary. All comments must be in English.",
        "user_en": "Send cute-style English danmu for this screenshot:",
    },
    "路人惊讶型": {
        "system_zh": "风格：像普通观众突然看到画面变化后的真实反应，语气惊讶、自然、有点好奇。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style: like a regular viewer's genuine reaction to something surprising on screen—astonished, natural, curious. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
    "搞笑玩梗型": {
        "system_zh": "风格：轻松搞笑，像直播间高频刷屏弹幕，有节目效果，但不要太尬。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style: light and funny, like high-frequency chat memes with good comedic timing, but not cringy. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
    "专业分析型": {
        "system_zh": "风格：像懂行观众在快速点评，简短、有信息量、但口语化，不要复杂术语。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style: like a knowledgeable viewer giving quick takes—brief, informative, but conversational, no jargon. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
    "捧场活跃型": {
        "system_zh": "风格：积极、热闹、会接话，像帮主播暖场的真实观众，不要夸张到虚假。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style: positive, lively, chatty—like a real viewer helping warm up the stream, but not fake-exaggerated. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
    "轻度吐槽型": {
        "system_zh": "风格：嘴上吐槽但不伤人，像真实观众的轻松调侃，不要人身攻击、低俗、恶意嘲讽。",
        "user_zh": "请基于这张截图生成弹幕：",
        "system_en": "Style: light roasting without hurting feelings, like a real viewer's playful teasing—no personal attacks, vulgarity, or malice. All comments must be in English.",
        "user_en": "Generate English danmu comments based on this screenshot:",
    },
}


def get_reply_contract() -> str:
    return REPLY_CONTRACT_EN if Translator.get_language() == "en" else REPLY_CONTRACT_ZH


def strip_reply_contract(system_pt: str) -> str:
    base = (system_pt or "").strip()
    for contract in REPLY_CONTRACT_ALIASES:
        if base.startswith(contract):
            return base[len(contract):].strip()
    return base


def ensure_reply_contract(system_pt: str) -> str:
    custom_part = strip_reply_contract(system_pt)
    contract = get_reply_contract()
    return f"{contract} {custom_part}".strip() if custom_part else contract


def normalize_persona_name(name: str) -> str:
    if not name:
        return ""
    return LEGACY_NAME_MAP.get(name, name)


def persona_display_name(name: str) -> str:
    normalized = normalize_persona_name(name)
    key = PERSONA_NAME_KEYS.get(normalized)
    return tr(key) if key else normalized


def default_user_prompt() -> str:
    return tr("template.default_user_prompt")


class PersonaManager:
    DEFAULT_ACTIVE = ["路人惊讶型", "搞笑玩梗型", "专业分析型", "捧场活跃型", "轻度吐槽型"]
    _ACTIVE_VERSION = 2

    def __init__(self, config: ConfigStore):
        self.config = config
        self._custom: dict = {}
        self._migrate_active_personae()

    def _migrate_active_personae(self):
        version = self.config.get_int("active_personae_version", 0)
        if version < self._ACTIVE_VERSION:
            self.config.set_json("active_personae", self.DEFAULT_ACTIVE)
            self.config.set("active_personae_version", str(self._ACTIVE_VERSION))

    def list(self) -> list[str]:
        builtin = list(BUILTIN_PERSONAE.keys())
        custom = self._load_custom_names()
        return builtin + custom

    def get_prompt(self, name: str) -> tuple[str, str]:
        normalized = normalize_persona_name(name)
        if normalized in BUILTIN_PERSONAE:
            prompt = BUILTIN_PERSONAE[normalized]
            if Translator.get_language() == "en":
                return ensure_reply_contract(prompt["system_en"]), prompt["user_en"]
            return ensure_reply_contract(prompt["system_zh"]), prompt["user_zh"]

        custom = self._load_custom()
        if normalized in custom:
            prompt = custom[normalized]
            return ensure_reply_contract(prompt["system_pt"]), prompt["user_pt"]
        return "", ""

    def get_active(self) -> list[str]:
        names = self.config.get_json("active_personae", self.DEFAULT_ACTIVE)
        normalized = [normalize_persona_name(name) for name in names]
        normalized = [name for name in normalized if name]
        return normalized or self.DEFAULT_ACTIVE

    def set_active(self, names: list[str]):
        normalized = [normalize_persona_name(name) for name in names if name]
        self.config.set_json("active_personae", normalized or self.DEFAULT_ACTIVE)

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
        custom = self._load_custom()
        custom.pop(normalize_persona_name(name), None)
        self._custom = custom
        self.config.set("custom_personae", json.dumps(custom, ensure_ascii=False))

    def pick_random(self) -> str:
        active = self.get_active()
        return random.choice(active) if active else self.DEFAULT_ACTIVE[0]
