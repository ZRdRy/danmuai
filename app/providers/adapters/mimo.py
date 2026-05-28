"""Xiaomi MiMo OpenAI-compatible adapter."""

from __future__ import annotations

from app.providers.adapters.default_openai import DefaultOpenAIAdapter
from app.providers.capabilities import ProviderCapabilities
from app.providers.constants import THINKING_DISABLED


class MimoOpenAIAdapter(DefaultOpenAIAdapter):
    def build_vision_user_content(self, user_pt: str, image_data_uri: str) -> list[dict]:
        image_part = {"type": "image_url", "image_url": {"url": image_data_uri}}
        text_part = {"type": "text", "text": user_pt}
        return [image_part, text_part]

    def patch_openai_chat_body(
        self,
        data: dict,
        *,
        max_tokens: int,
        caps: ProviderCapabilities,
    ) -> None:
        data.pop("max_tokens", None)
        data.pop("stream_options", None)
        if caps.thinking_param:
            data["thinking"] = dict(THINKING_DISABLED)
        if max_tokens > 0:
            data[caps.max_tokens_field] = max_tokens

    def patch_probe_body(self, data: dict, *, caps: ProviderCapabilities) -> None:
        if "max_tokens" not in data:
            if caps.thinking_param:
                data["thinking"] = dict(THINKING_DISABLED)
            return
        max_tokens = int(data.pop("max_tokens") or 1)
        self.patch_openai_chat_body(data, max_tokens=max_tokens, caps=caps)
