from __future__ import annotations

import json
import random
import re

from app.config_store import ConfigStore
from app.danmu_engine import (
    DEFAULT_DANMU_MAX_CHARS_EN,
    DEFAULT_DANMU_MAX_CHARS_ZH,
    resolve_danmu_max_chars,
)
from app.translations import Translator, tr

REPLY_COUNT_MIN = 2
REPLY_COUNT_MAX = 7
DEFAULT_REPLY_SCENE_COUNT = 2
DEFAULT_REPLY_FILLER_COUNT = 3

DEFAULT_NORMAL_REPLY_COUNT = 5
NORMAL_REPLY_COUNT_MIN = 1
NORMAL_REPLY_COUNT_MAX = 20

_CONTRACT_ZH_RE = re.compile(
    r"你是直播弹幕评论员。必须且只能返回 JSON 字符串数组，不要解释，不要 Markdown。"
    r"固定返回 \d+ 条弹幕：前 \d+ 条必须强相关当前画面，后 \d+ 条必须是适合直播间氛围的泛用弹幕。"
    r"每条不超过 \d+ 个字，避免重复，输出格式："
    r'\["[^"]*"(?:, "[^"]*")*\]。'
)
_CONTRACT_EN_RE = re.compile(
    r"You are a live-stream danmu commentator\. You must return a JSON string array only, "
    r"with no explanations and no Markdown\. "
    r"Always return exactly \d+ comments: the first \d+ must be strongly tied to the current frame, "
    r"and the last \d+ must be generic danmu suitable for a live-stream atmosphere\. "
    r"All comments MUST be written in English only\. "
    r"Each comment must stay within \d+ characters\. Avoid repetition\. Output format: "
    r'\["[^"]*"(?:, "[^"]*")*\]\.'
)
_CONTRACT_NORMAL_ZH_RE = re.compile(
    r"直播弹幕评论员。只输出 JSON 字符串数组，无解释、无 Markdown。"
    r"固定 \d+ 条，每条≤\d+字。"
    r"像多位真实观众：短句口语碎片化；优先贴当前画面，可少量接梗或气氛句；条间口吻可不同。"
    r"禁 AI腔/总结腔/客服腔/长句/说教/重复。"
    r"格式："
    r'\["[^"]*"(?:, "[^"]*")*\]。'
)
_CONTRACT_NORMAL_ZH_LEGACY_RE = re.compile(
    r"你是直播弹幕评论员。必须且只能返回 JSON 字符串数组，不要解释，不要 Markdown。"
    r"固定返回 \d+ 条弹幕，必须与当前画面或直播氛围相关，避免重复。"
    r"每条不超过 \d+ 个字，输出格式："
    r'\["[^"]*"(?:, "[^"]*")*\]。'
)
_CONTRACT_NORMAL_EN_RE = re.compile(
    r"Live-stream danmu commentator\. JSON string array only, no explanation, no Markdown\. "
    r"Exactly \d+ comments, max \d+ chars each\. "
    r"Multiple real viewers: short, casual, fragmented; prioritize the current frame; "
    r"a few meme or vibe lines OK; vary voice per line\. "
    r"No AI tone, summaries, customer-service voice, long lines, preaching, or repetition\. "
    r"All comments MUST be in English only\. "
    r"Format: "
    r'\["[^"]*"(?:, "[^"]*")*\]\.'
)
_CONTRACT_NORMAL_EN_LEGACY_RE = re.compile(
    r"You are a live-stream danmu commentator\. You must return a JSON string array only, "
    r"with no explanations and no Markdown\. "
    r"Always return exactly \d+ comments that must relate to the current frame or live-stream atmosphere\. "
    r"Avoid repetition\. All comments MUST be written in English only\. "
    r"Each comment must stay within \d+ characters\. Output format: "
    r'\["[^"]*"(?:, "[^"]*")*\]\.'
)

REPLY_CONTRACT_ZH = ""
REPLY_CONTRACT_EN = ""
REPLY_CONTRACT_ALIASES: set[str] = set()
REPLY_CONTRACT = ""


def _clamp_reply_count(value: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(REPLY_COUNT_MIN, min(REPLY_COUNT_MAX, n))


def reply_counts_from_config(config: ConfigStore | None) -> tuple[int, int]:
    if config is None:
        return DEFAULT_REPLY_SCENE_COUNT, DEFAULT_REPLY_FILLER_COUNT
    scene = _clamp_reply_count(
        config.get_int("reply_scene_count", DEFAULT_REPLY_SCENE_COUNT),
        DEFAULT_REPLY_SCENE_COUNT,
    )
    filler = _clamp_reply_count(
        config.get_int("reply_filler_count", DEFAULT_REPLY_FILLER_COUNT),
        DEFAULT_REPLY_FILLER_COUNT,
    )
    return scene, filler


def _clamp_normal_reply_count(value: int, default: int = DEFAULT_NORMAL_REPLY_COUNT) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(NORMAL_REPLY_COUNT_MIN, min(NORMAL_REPLY_COUNT_MAX, n))


def normal_reply_count_from_config(config: ConfigStore | None) -> int:
    if config is None:
        return DEFAULT_NORMAL_REPLY_COUNT
    return _clamp_normal_reply_count(
        config.get_int("normal_reply_count", DEFAULT_NORMAL_REPLY_COUNT),
        DEFAULT_NORMAL_REPLY_COUNT,
    )


def _json_example_zh(total: int) -> str:
    items = [f"弹幕{i}" for i in range(1, total + 1)]
    return '["' + '", "'.join(items) + '"]'


def _json_example_en(total: int) -> str:
    items = [f"comment {i}" for i in range(1, total + 1)]
    return '["' + '", "'.join(items) + '"]'


def build_reply_contract_zh(
    scene_count: int,
    filler_count: int,
    max_chars: int | None = None,
) -> str:
    scene = _clamp_reply_count(scene_count, DEFAULT_REPLY_SCENE_COUNT)
    filler = _clamp_reply_count(filler_count, DEFAULT_REPLY_FILLER_COUNT)
    total = scene + filler
    limit = max_chars if max_chars is not None else DEFAULT_DANMU_MAX_CHARS_ZH
    return (
        "你是直播弹幕评论员。必须且只能返回 JSON 字符串数组，不要解释，不要 Markdown。"
        f"固定返回 {total} 条弹幕：前 {scene} 条必须强相关当前画面，后 {filler} 条必须是适合直播间氛围的泛用弹幕。"
        f"每条不超过 {limit} 个字，避免重复，输出格式："
        f"{_json_example_zh(total)}。"
    )


def build_reply_contract_en(
    scene_count: int,
    filler_count: int,
    max_chars: int | None = None,
) -> str:
    scene = _clamp_reply_count(scene_count, DEFAULT_REPLY_SCENE_COUNT)
    filler = _clamp_reply_count(filler_count, DEFAULT_REPLY_FILLER_COUNT)
    total = scene + filler
    limit = max_chars if max_chars is not None else DEFAULT_DANMU_MAX_CHARS_EN
    return (
        "You are a live-stream danmu commentator. You must return a JSON string array only, "
        "with no explanations and no Markdown. "
        f"Always return exactly {total} comments: the first {scene} must be strongly tied to the current frame, "
        f"and the last {filler} must be generic danmu suitable for a live-stream atmosphere. "
        "All comments MUST be written in English only. "
        f"Each comment must stay within {limit} characters. Avoid repetition. Output format: "
        f"{_json_example_en(total)}."
    )


def build_normal_reply_contract_zh(
    count: int,
    max_chars: int | None = None,
) -> str:
    total = _clamp_normal_reply_count(count, DEFAULT_NORMAL_REPLY_COUNT)
    limit = max_chars if max_chars is not None else DEFAULT_DANMU_MAX_CHARS_ZH
    return (
        "直播弹幕评论员。只输出 JSON 字符串数组，无解释、无 Markdown。"
        f"固定 {total} 条，每条≤{limit}字。"
        "像多位真实观众：短句口语碎片化；优先贴当前画面，可少量接梗或气氛句；条间口吻可不同。"
        "禁 AI腔/总结腔/客服腔/长句/说教/重复。"
        f"格式：{_json_example_zh(total)}。"
    )


def build_normal_reply_contract_en(
    count: int,
    max_chars: int | None = None,
) -> str:
    total = _clamp_normal_reply_count(count, DEFAULT_NORMAL_REPLY_COUNT)
    limit = max_chars if max_chars is not None else DEFAULT_DANMU_MAX_CHARS_EN
    return (
        "Live-stream danmu commentator. JSON string array only, no explanation, no Markdown. "
        f"Exactly {total} comments, max {limit} chars each. "
        "Multiple real viewers: short, casual, fragmented; prioritize the current frame; "
        "a few meme or vibe lines OK; vary voice per line. "
        "No AI tone, summaries, customer-service voice, long lines, preaching, or repetition. "
        "All comments MUST be in English only. "
        f"Format: {_json_example_en(total)}."
    )


def _refresh_legacy_contract_aliases() -> None:
    global REPLY_CONTRACT_ZH, REPLY_CONTRACT_EN, REPLY_CONTRACT, REPLY_CONTRACT_ALIASES
    REPLY_CONTRACT_ZH = build_reply_contract_zh(
        DEFAULT_REPLY_SCENE_COUNT,
        DEFAULT_REPLY_FILLER_COUNT,
        DEFAULT_DANMU_MAX_CHARS_ZH,
    )
    REPLY_CONTRACT_EN = build_reply_contract_en(
        DEFAULT_REPLY_SCENE_COUNT,
        DEFAULT_REPLY_FILLER_COUNT,
        DEFAULT_DANMU_MAX_CHARS_EN,
    )
    REPLY_CONTRACT = REPLY_CONTRACT_ZH
    normal_zh = build_normal_reply_contract_zh(DEFAULT_NORMAL_REPLY_COUNT, DEFAULT_DANMU_MAX_CHARS_ZH)
    normal_en = build_normal_reply_contract_en(DEFAULT_NORMAL_REPLY_COUNT, DEFAULT_DANMU_MAX_CHARS_EN)
    REPLY_CONTRACT_ALIASES = {REPLY_CONTRACT_ZH, REPLY_CONTRACT_EN, normal_zh, normal_en}


_refresh_legacy_contract_aliases()


def get_reply_contract(config: ConfigStore | None = None) -> str:
    lang = Translator.get_language()
    if config is None:
        max_chars = (
            DEFAULT_DANMU_MAX_CHARS_EN if lang == "en" else DEFAULT_DANMU_MAX_CHARS_ZH
        )
    else:
        max_chars = resolve_danmu_max_chars(config, lang=lang)
    count = normal_reply_count_from_config(config)
    if lang == "en":
        return build_normal_reply_contract_en(count, max_chars)
    return build_normal_reply_contract_zh(count, max_chars)


def strip_reply_contract(system_pt: str) -> str:
    base = (system_pt or "").strip()
    for pattern in (
        _CONTRACT_ZH_RE,
        _CONTRACT_EN_RE,
        _CONTRACT_NORMAL_ZH_RE,
        _CONTRACT_NORMAL_ZH_LEGACY_RE,
        _CONTRACT_NORMAL_EN_RE,
        _CONTRACT_NORMAL_EN_LEGACY_RE,
    ):
        base = pattern.sub("", base).strip()
    for contract in REPLY_CONTRACT_ALIASES:
        if base.startswith(contract):
            base = base[len(contract) :].strip()
    return base


def ensure_reply_contract(system_pt: str, config: ConfigStore | None = None) -> str:
    custom_part = strip_reply_contract(system_pt)
    contract = get_reply_contract(config)
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


_REMOVED_PERSONAE = frozenset({"阿静", "测试"})

BUILTIN_PERSONA_PINNED_FIRST = ("测试1", "测试2", "测试3", "测试4")


def _builtin_personae_names() -> list[str]:
    pinned = [n for n in BUILTIN_PERSONA_PINNED_FIRST if n in BUILTIN_PERSONAE]
    rest = [n for n in BUILTIN_PERSONAE if n not in pinned]
    return pinned + rest

LEGACY_NAME_MAP = {
    "閸氭劖蝎閸?": "吐槽型",
    "閺傚洩澹撻崹?": "文艺型",
    "閹垛偓閺堫垰鐎?": "技术型",
    "閽€宀€閮撮崹?": "萌系型",
}

PERSONA_NAME_KEYS = {
    "吐槽型": "persona.roast",
    "文艺型": "persona.poetic",
    "技术型": "persona.tech",
    "萌系型": "persona.cute",
    "路人惊讶型": "persona.surprised",
    "搞笑玩梗型": "persona.meme",
    "专业分析型": "persona.analyst",
    "捧场活跃型": "persona.cheerleader",
    "轻度吐槽型": "persona.light_roast",
    "傲娇型": "persona.tsundere",
    "腹黑型": "persona.scheming",
    "中二型": "persona.chuuni",
    "治愈型": "persona.healing",
    "毒舌型": "persona.sharp",
    "元气型": "persona.genki",
    "社恐型": "persona.shy",
    "测试1": "persona.test1",
    "测试2": "persona.test2",
    "测试3": "persona.test3",
    "测试4": "persona.test4",
}

BUILTIN_PERSONAE = {
    "吐槽型": {
        "system_zh": "嘴碎吐槽党，不人身攻击。",
        "user_zh": "看图发弹幕：",
        "system_en": "Snarky roaster, never personal.",
        "user_en": "Danmu for screenshot:",
    },
    "文艺型": {
        "system_zh": "文艺观众，有画面感，不堆砌。",
        "user_zh": "看图发弹幕：",
        "system_en": "Poetic viewer, imagery over fluff.",
        "user_en": "Danmu for screenshot:",
    },
    "技术型": {
        "system_zh": "懂行观众快评，口语不讲术语。",
        "user_zh": "看图发弹幕：",
        "system_en": "Tech-savvy viewer, plain words.",
        "user_en": "Danmu for screenshot:",
    },
    "萌系型": {
        "system_zh": "可爱观众，轻松不撒娇过头。",
        "user_zh": "看图发弹幕：",
        "system_en": "Cute viewer, light not sugary.",
        "user_en": "Danmu for screenshot:",
    },
    "路人惊讶型": {
        "system_zh": "路人观众，画面一变就惊讶好奇。",
        "user_zh": "看图发弹幕：",
        "system_en": "Bystander viewer, surprised by screen changes.",
        "user_en": "Danmu for screenshot:",
    },
    "搞笑玩梗型": {
        "system_zh": "玩梗乐子人，有节目效果别太尬。",
        "user_zh": "看图发弹幕：",
        "system_en": "Meme lord, funny not cringy.",
        "user_en": "Danmu for screenshot:",
    },
    "专业分析型": {
        "system_zh": "懂行随口快评，短句口语。",
        "user_zh": "看图发弹幕：",
        "system_en": "Know-it-all viewer, quick casual takes.",
        "user_en": "Danmu for screenshot:",
    },
    "捧场活跃型": {
        "system_zh": "热心捧场接话，不假嗨。",
        "user_zh": "看图发弹幕：",
        "system_en": "Hype viewer, warm not fake.",
        "user_en": "Danmu for screenshot:",
    },
    "轻度吐槽型": {
        "system_zh": "轻松调侃，不伤人。",
        "user_zh": "看图发弹幕：",
        "system_en": "Light roast, playful not mean.",
        "user_en": "Danmu for screenshot:",
    },
    "傲娇型": {
        "system_zh": "嘴硬心软傲娇，不骂主播。",
        "user_zh": "看图发弹幕：",
        "system_en": "Tsundere viewer, dismissive but fair.",
        "user_en": "Danmu for screenshot:",
    },
    "腹黑型": {
        "system_zh": "表面客气，暗戳笑点。",
        "user_zh": "看图发弹幕：",
        "system_en": "Polite outside, subtle jabs inside.",
        "user_en": "Danmu for screenshot:",
    },
    "中二型": {
        "system_zh": "中二热血接话，别尬。",
        "user_zh": "看图发弹幕：",
        "system_en": "Chuunibyou hype, dramatic not cringy.",
        "user_en": "Danmu for screenshot:",
    },
    "治愈型": {
        "system_zh": "温柔鼓励，不鸡汤不说教。",
        "user_zh": "看图发弹幕：",
        "system_en": "Comforting viewer, warm not preachy.",
        "user_en": "Danmu for screenshot:",
    },
    "毒舌型": {
        "system_zh": "犀利短评，不人身不低俗。",
        "user_zh": "看图发弹幕：",
        "system_en": "Sharp one-liners, no malice.",
        "user_en": "Danmu for screenshot:",
    },
    "元气型": {
        "system_zh": "高能量打气，不假嗨。",
        "user_zh": "看图发弹幕：",
        "system_en": "High-energy cheer, genuine hype.",
        "user_en": "Danmu for screenshot:",
    },
    "社恐型": {
        "system_zh": "小声害羞嘀咕，不阴阳。",
        "user_zh": "看图发弹幕：",
        "system_en": "Shy mutter, hesitant and gentle.",
        "user_en": "Danmu for screenshot:",
    },
    "测试1": {
        "system_zh": (
            "【人格：真实直播间五人弹幕】"
            "发言随意、情绪化、碎片化、带网梗。"
            "固定 5 条弹幕，按顺序各对应 1 个角色，口吻必须明显不同："
            "1. 玩梗乐子人：套流行梗/谐音梗，别正经。（例：这波是顶级理解、纯纯的依托答辩、优雅太优雅了）"
            "2. 无脑复读机：符号/单字/短词刷屏，可错别字。（例：？？？？？？、草、好好好这么玩是吧）"
            "3. 大惊小怪粉：情绪炸裂、极短。（例：卧槽快跑、这也能活、主播糊涂啊）"
            "4. 键盘侠/黑粉：挑操作、阴阳、苛刻。（例：就这我上我也行、急了红温了、经典下饭看饱了）"
            "5. 懵逼路人：弱智疑问或无厘头。（例：刚才发生了啥、怎么又死了、这主播是人）"
            "【严禁】"
            "主播你、很遗憾、请注意、从画面可以看出、表现得很好、建议；完整教科书长句。"
            "【风格对照】"
            "AI：主播在玩格斗游戏，画面很激烈。→ 真人：龟龟，这拳拳到肉啊"
            "AI：失败了请加油。→ 真人：下饭下饭今晚不用吃晚饭了"
            "AI：前方有危险请注意。→ 真人：危 危 危 危 危"
            "AI：深夜了要注意休息。→ 真人：修仙党狂喜"
        ),
        "user_zh": "看图发弹幕：",
        "system_en": (
            "Five live-stream viewers, distinct voices per line: "
            "meme lord, spam repeater, hype fan, harsh critic, clueless bystander. "
            "Casual, fragmented, slang-heavy. No AI assistant tone or textbook sentences. "
            "All comments in English."
        ),
        "user_en": "Danmu for screenshot:",
    },
    "测试2": {
        "system_zh": (
            "【人格：竞技操作五人弹幕】"
            "发言像看排位/团战的观众，口语碎片、带梗。"
            "固定 5 条，按顺序各 1 角色，口吻明显不同："
            "1. 神操作吹：夸张夸操作。（例：离谱、教科书、这波天秀）"
            "2. 下饭吐槽：菜、送、白给。（例：看饱了、经典下饭、又送了）"
            "3. 口头教练：短句指挥。（例：该撤了、别贪、别追了）"
            "4. 退游观众：不想看了。（例：走了、不看了、关了关了）"
            "5. 云玩家：我上我也行。（例：这不有手就行、换我来）"
            "【严禁】"
            "主播你、很遗憾、请注意、从画面可以看出、表现得很好、建议；完整教科书长句。"
            "【风格对照】"
            "AI：这波团灭很可惜。→ 真人：经典四打五送完"
            "AI：操作需要更谨慎。→ 真人：又白给了哥"
            "AI：建议撤退保存实力。→ 真人：跑啊别送了"
            "AI：观众可以休息一下。→ 真人：退了退了"
        ),
        "user_zh": "看图发弹幕：",
        "system_en": (
            "Five esports viewers: hype plays, roast feeds, quick calls, quit-watching, cloud gaming. "
            "Short casual lines tied to the frame. No coaching tone or textbook sentences. English only."
        ),
        "user_en": "Danmu for screenshot:",
    },
    "测试3": {
        "system_zh": (
            "【人格：氛围唠嗑五人弹幕】"
            "发言像边挂直播边聊天的网友，常跑题、吃瓜、犯困。"
            "固定 5 条，按顺序各 1 角色，口吻明显不同："
            "1. 跑题唠嗑：外卖作业摸鱼。（例：饿了、作业没写、摸鱼中）"
            "2. 吃瓜围观：？？？前排。（例：？？？、前排出售瓜子、来了来了）"
            "3. 修仙困觉：几点了还不睡。（例：几点了、主播还不睡、困死了）"
            "4. 抬杠怪：就你懂真的假的。（例：真的假的、就你懂、呵呵）"
            "5. 纯表情语气：啊啊啊 hhhh 6。（例：啊啊啊、hhhh、6）"
            "【严禁】"
            "主播你、很遗憾、请注意、从画面可以看出、表现得很好、建议；完整教科书长句。"
            "【风格对照】"
            "AI：直播间氛围很轻松。→ 真人：摸鱼快乐"
            "AI：发生了有趣的事。→ 真人：？？？发生啥了"
            "AI：时间很晚了。→ 真人：修仙党集合"
            "AI：请不要争吵。→ 真人：就你懂是吧"
        ),
        "user_zh": "看图发弹幕：",
        "system_en": (
            "Five chatty viewers: off-topic chatter, popcorn crowd, late-night tired, contrarian, "
            "emoji bursts. Casual fragmented lines. No AI tone. English only."
        ),
        "user_en": "Danmu for screenshot:",
    },
    "测试4": {
        "system_zh": (
            "【人格：阴阳梗典五人弹幕】"
            "发言阴阳、玩梗、懂哥、挑刺、突然笑场。"
            "固定 5 条，按顺序各 1 角色，口吻明显不同："
            "1. 阴阳大师：反讽不错不错。（例：不错不错、可以可以、挺好的）"
            "2. 复制梗：典绷难评赢麻。（例：典、绷不住了、难评、赢麻了）"
            "3. 懂哥：其实应该半句。（例：其实应该、懂哥来了）"
            "4. 挑刺杠：鸡蛋里挑骨头。（例：这也能、就这、不行吧）"
            "5. 突发笑场：莫名其妙哈哈。（例：哈哈、？、笑死）"
            "【严禁】"
            "主播你、很遗憾、请注意、从画面可以看出、表现得很好、建议；完整教科书长句。"
            "【风格对照】"
            "AI：主播表现还可以。→ 真人：不错不错（阴阳）"
            "AI：这局很难评价。→ 真人：难评，典"
            "AI：应该这样操作更好。→ 真人：懂哥来了"
            "AI：有一个小失误。→ 真人：就这？"
        ),
        "user_zh": "看图发弹幕：",
        "system_en": (
            "Five sarcastic viewers: passive-aggressive praise, meme catchphrases, know-it-all half-takes, "
            "nitpicks, random laughter. Short fragmented lines. No AI tone. English only."
        ),
        "user_en": "Danmu for screenshot:",
    },
}


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
        return _builtin_personae_names() + custom

    def get_prompt(self, name: str) -> tuple[str, str]:
        normalized = normalize_persona_name(name)
        custom = self._load_custom()
        if normalized in custom:
            prompt = custom[normalized]
            system_pt = (prompt.get("system_pt") or "").strip()
            if system_pt:
                user_pt = prompt.get("user_pt") or default_user_prompt()
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
        return normalized

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
        custom = self._load_custom()
        custom.pop(normalize_persona_name(name), None)
        self._custom = custom
        self.config.set("custom_personae", json.dumps(custom, ensure_ascii=False))

    def pick_random(self) -> str:
        active = self.get_active()
        return random.choice(active) if active else self.DEFAULT_ACTIVE[0]
