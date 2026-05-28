"""OpenAI Chat Completions adapter protocol."""

from __future__ import annotations

from typing import Protocol

from app.providers.capabilities import ProviderCapabilities


class ProviderAdapter(Protocol):
    def build_vision_user_content(self, user_pt: str, image_data_uri: str) -> list[dict]:
        ...

    def patch_openai_chat_body(
        self,
        data: dict,
        *,
        max_tokens: int,
        caps: ProviderCapabilities,
    ) -> None:
        ...

    def patch_probe_body(self, data: dict, *, caps: ProviderCapabilities) -> None:
        ...

    def normalize_usage(self, usage: dict | None, *, caps: ProviderCapabilities) -> tuple[int, int]:
        ...
