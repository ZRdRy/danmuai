# Provider 适配层

> W-PROVIDER-ADAPTER-001。学习 LiteLLM 的注册表 + 适配器思路，**不引入** `litellm` 依赖。

## 结构

```text
app/providers/
├─ registry.py       # HOST_ENTRIES（从 PROVIDERS 派生）→ guess / transport
├─ capabilities.py   # ProviderCapabilities 按 provider_id
├─ constants.py      # THINKING_DISABLED（避免与 ai_client 循环导入）
└─ adapters/
   ├─ default_openai.py  # 通用 OpenAI-compat
   └─ mimo.py             # 小米 MiMo 特例
```

`app/model_providers.py` 仍导出 `ProviderSpec` / `PROVIDERS`；`guess_provider_from_endpoint` 与 `resolve_api_transport` 委托 `registry`。

`app/ai_client.py` 保留 HTTP/SSE 主流程；OpenAI-compat 请求体补丁委托 `get_openai_adapter()`。

## ProviderCapabilities 字段

| 字段 | 含义 |
|------|------|
| `transport` | `doubao`（Responses）或 `openai`（Chat Completions） |
| `vision` | 支持截图识图（预留，默认 true） |
| `mic_audio` | Responses `input_audio`（豆包；运行时仍用 `model_likely_supports_mic_audio`） |
| `thinking_param` | 顶层 `thinking: disabled`（MiMo） |
| `image_before_text` | 多模态 user content 顺序 |
| `stream_usage_in_final_chunk` | `stream_options.include_usage` |
| `max_tokens_field` | `max_tokens` 或 `max_completion_tokens` |
| `usage_token_style` | `openai` 或 `dashscope`（SSE usage 字段名） |

## 新增 OpenAI-compat 服务商 checklist

1. 在 `app/model_providers.py` 的 `PROVIDERS` 增加 `ProviderSpec`（含 `default_endpoint`）。
2. 在 `app/providers/capabilities.py` 的 `_register(...)` 声明能力（无怪癖则省略，用默认）。
3. `HOST_ENTRIES` 自动从 `default_endpoint` 的 netloc 生成，无需再维护 `_ENDPOINT_GUESSES` / host marker 三表。
4. 若有 HTTP 体怪癖：新增 `adapters/*.py` 并在 `get_openai_adapter()` 中按 `provider_id` 选择。
5. 补充 `tests/test_provider_adapters.py` 与 `tests/test_model_providers.py` 用例。

## 暂不在适配层的内容

- 豆包 Responses 请求体（`_request_doubao`）
- 主链路截图 / 人格 / 记忆 / 回复队列（`main.py`）
- `app/model_catalog.py` 模型目录与定价

## 已知限制

- ISSUE-005：MiMo 连通性探测仍为纯文本 ping，不含识图（范围外）。
