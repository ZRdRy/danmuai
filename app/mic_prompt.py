"""Prompt helpers when microphone insert mode is enabled.

``build_mic_insert_user_pt`` 把 ``MIC_INSERT_BLOCK`` 拼到用户提示词末尾，告诉 AI
「用户刚说完一句话，请同时回应语音和截图」。仅在 ``mic_mode_enabled`` 与
``model_supports_mic_audio`` 同时为真时由 ``_trigger_mic_api_call`` 调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config_store import ConfigStore

MIC_INSERT_BLOCK = (
    "【麦克风插入】用户刚说完一句话，附带了真实语音。"
    "请生成 6条 JSON 数组弹幕。"
    "前3条必须直接回应用户刚才说了什么（复述要点、接话、提问或吐槽均可）；"
    "后 3 条可结合截图氛围。"
    "若语音与截图无关，仍要在前 2 条体现听到了用户说话，不要只描述截图。"
)


def build_mic_insert_user_pt(user_pt: str, config: "ConfigStore | None" = None) -> str:
    del config
    block = MIC_INSERT_BLOCK
    base = (user_pt or "").rstrip()
    if not base:
        return block
    return f"{base}\n\n{block}"
