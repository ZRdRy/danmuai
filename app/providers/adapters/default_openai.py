"""Default OpenAI-compatible adapter (text before image, max_tokens, stream usage).

适用范围：除小米 MiMo 之外的所有 OpenAI 兼容 provider（火山方舟/百炼/智谱/Moonshot/硅基流动/自定义 OpenAI）。

关键差异（与 ``MimoOpenAIAdapter`` 对比）：
- 视觉 user content 顺序为 ``[text, image]``（部分 provider 期望文本先于图片）。
- ``stream_options`` 注入条件：仅当 ``caps.stream_usage_in_final_chunk`` 为真
  且请求 ``stream: true`` 时注入 ``{"include_usage": True}``，避免百炼在非流式下 400（见 W-021）。
- 麦克风音频（``audio_data_uri``）不直接附加到 user content；上层走 ``ai_butler`` 等独立路由。
"""

from __future__ import annotations

from app.providers.capabilities import ProviderCapabilities


class DefaultOpenAIAdapter:
    def build_vision_user_content(
        self,
        user_pt: str,
        image_data_uri: str,
        audio_data_uri: str | None = None,
    ) -> list[dict]:
        image_part = {"type": "image_url", "image_url": {"url": image_data_uri}}
        text_part = {"type": "text", "text": user_pt}
        return [text_part, image_part]

    def patch_openai_chat_body(
        self,
        data: dict,
        *,
        max_tokens: int,
        caps: ProviderCapabilities,
    ) -> None:
        if max_tokens > 0:
            data[caps.max_tokens_field] = max_tokens
        # 仅 stream: true 时才注入 stream_options；非流式下百炼会返回 400
        if caps.stream_usage_in_final_chunk and data.get("stream"):
            data["stream_options"] = {"include_usage": True}
        else:
            data.pop("stream_options", None)

    def patch_probe_body(self, data: dict, *, caps: ProviderCapabilities) -> None:
        if "max_tokens" not in data:
            return
        max_tokens = int(data.pop("max_tokens") or 1)
        self.patch_openai_chat_body(data, max_tokens=max_tokens, caps=caps)

    def normalize_usage(self, usage: dict | None, *, caps: ProviderCapabilities) -> tuple[int, int]:
        if not usage:
            return 0, 0
        if caps.usage_token_style == "dashscope":
            return int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        if prompt is None and completion is None:
            prompt = usage.get("input_tokens", 0)
            completion = usage.get("output_tokens", 0)
        return int(prompt or 0), int(completion or 0)
