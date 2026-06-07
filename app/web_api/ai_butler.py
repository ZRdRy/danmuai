"""AI 管家：纯文本对话辅助理解/建议助手设置（不经主链路 AiWorker）。

设计原则：
- 17 字段白名单（``AI_BUTLER_ALLOWED_KEYS``）：管家只能读/建议这 17 个键，patch 写入也
  限制在白名单内，避免误改主配置或泄漏 ``api_key``。
- 不经主链路 ``AiWorker`` / ``ai_in_flight``：管家是旁路 HTTP 线程调用（独立 client），
  不会阻塞视觉截图主链路；与主链路并发安全。
- 走 ``/chat/completions``（OpenAI 兼容） 或 ``/responses``（豆包）双协议；由
  ``resolve_api_transport`` 自动选。
- 返回结构 ``ButlerParseResult``：``reply`` 自然语言回复 + ``patch`` 字段调整建议
  （经 Web 端弹窗让用户确认，不直接落配置）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from app.ai_client import THINKING_DISABLED, format_http_status_error
from app.application.config_service import _clamp_choice, _clamp_int_key
from app.config_defaults import config_value_with_default
from app.doubao_responses_stream import extract_text_from_response
from app.model_providers import normalize_endpoint, normalize_mode, resolve_api_transport
from app.providers import get_capabilities_for_endpoint, get_openai_adapter
from app.translations import tr

if TYPE_CHECKING:
    from main import DanmuApp

# 17 字段白名单：patch 只能命中这里；非白名单键一律忽略（防止管家改 api_key/自定义模型等敏感项）
AI_BUTLER_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "temperature",
        "max_tokens",
        "danmu_speed",
        "danmu_lines",
        "danmu_max_chars",
        "dedup_threshold",
        "layout_mode",
        "opacity",
        "font_size",
        "eviction_mode",
        "empty_accel",
        "image_max_width",
        "image_quality",
        "memory_mode",
        "memory_window",
        "normal_recognition_interval_sec",
        "normal_reply_count",
    }
)

BUTLER_MAX_OUTPUT_TOKENS = 2048
BUTLER_HISTORY_MAX_TURNS = 10
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

_FIELD_CATALOG = """
可调字段说明（patch 只能使用下列键，值为字符串）：
- temperature：创意程度 0–2，越高越发散
- max_tokens：单次 AI 输出 token 上限，建议 512 起
- danmu_speed：弹幕横向速度约 0.5–5，越大越快；调慢则减小
- danmu_lines：轨道行数 12–20
- danmu_max_chars：单条字数 5–80
- dedup_threshold：去重相似度 0–1，越高越容易判重复
- layout_mode：fullscreen / 3/4 / 1/2 / 1/4
- opacity：透明度 0–100
- font_size：字号约 12–72
- eviction_mode：natural（自然）或 accelerate（加速退场）
- empty_accel：0 或 1，空轨道加速补位
- image_max_width：截图最大宽度像素，越小越省 token
- image_quality：JPEG 质量 1–100
- memory_mode：off / dedup_only / scene_card / strong
- memory_window：记忆条数 1–20
- normal_recognition_interval_sec：识图间隔秒 1–60
- normal_reply_count：每批弹幕条数 1–20
"""


@dataclass
class ButlerParseResult:
    reply: str
    patch: dict[str, str]
    reasons: dict[str, str]
    needs_confirmation: bool


def ensure_api_configured(config) -> tuple[str, str, str, str]:
    endpoint = normalize_endpoint(config.get("api_endpoint", ""))
    api_key = (config.get_api_key() or "").strip()
    model = (config.get("model", "") or "").strip()
    mode = normalize_mode(config.get("api_mode", "doubao"))
    if not api_key or not model:
        raise ValueError("请先在「助手设置」中配置 API Key 与视觉模型后再使用 AI 管家。")
    if not endpoint:
        raise ValueError("请先在「助手设置」中填写 API Endpoint。")
    return endpoint, api_key, model, mode


def current_allowed_config_snapshot(config) -> dict[str, str]:
    return {
        key: config_value_with_default(config, key)
        for key in sorted(AI_BUTLER_ALLOWED_KEYS)
    }


def build_product_knowledge(config) -> str:
    """从代码生成 DanmuAI 使用/排障事实，注入系统提示词，减少幻觉。"""
    from app.model_providers import PROVIDERS
    from app.model_selection import resolve_model_status

    preset_lines: list[str] = []
    for spec in PROVIDERS:
        if spec.id.startswith("custom_"):
            continue
        preset_lines.append(
            f"- {spec.label_zh}（id={spec.id}）：默认地址 {spec.default_endpoint}；"
            f"api_mode={spec.mode}；模型提示：{spec.model_id_hint_zh}"
        )

    status = resolve_model_status(config)
    endpoint = (config.get("api_endpoint") or "").strip()
    model = (config.get("model") or "").strip()
    api_mode = (config.get("api_mode") or "").strip()
    mismatch = bool(status.get("provider_model_mismatch"))
    uses_custom = bool(status.get("uses_custom_credentials"))

    user_ctx = [
        f"api_endpoint: {endpoint or '（未填）'}",
        f"api_mode: {api_mode or '（未填）'}",
        f"model: {model or '（未填）'}",
        f"inferred_provider_id: {status.get('inferred_provider_id') or 'unknown'}",
        f"model_source: {status.get('model_source') or 'unknown'}",
        f"model_display_name: {status.get('model_display_name') or ''}",
        f"provider_model_mismatch: {mismatch}",
        f"uses_custom_credentials: {uses_custom}",
        f"has_api_key: {bool(config.get_api_key())}",
    ]

    troubleshooting = """
排障与使用说明要点（回答用户问题时必须遵守，勿编造）：
- DanmuAI 截图弹幕主链路需要**视觉/识图模型**；纯文本对话模型（如部分 deepseek-chat）无法识图生成弹幕。
- 助手设置「服务商」下拉**没有 DeepSeek 官方预设**；若用户问 DeepSeek：
  1) 可在「硅基流动」选带 deepseek 前缀的视觉模型 ID（如 deepseek-ai/DeepSeek-V3，以目录为准）；
  2) 或选「自定义（OpenAI 兼容）」填 DeepSeek 文档中的 API 地址与**支持识图**的模型 ID。
- 保存配置时：若 API 地址对应平台有模型目录，所选 model 须在目录内，否则保存失败（provider_model_mismatch）。
- 请在「助手设置」用「测试连接」验证 Key/地址/模型；401/402/404 等按返回说明排查。
- 「自定义模型」可单独保存 endpoint/Key/model；设为默认后全局地址/密钥可能不用于生成弹幕。
- 开麦实验功能：豆包全模态或小米 MiMo mimo-v2.5；与管家 patch 无关。
- 「读弹幕」使用独立 MiMo TTS Key（mimo-v2.5-tts），与视觉 API Key 分开，在「读弹幕」页配置。
- 「人格工坊」「公式化弹幕库」「识图区域鼠标框选」不在 AI 管家 patch 范围；用文字引导用户去对应侧栏页。
- 默认 UI：Web 控制台 + 弹幕 Overlay；遗留 Qt 主窗已移除。
"""

    return (
        "【DanmuAI 产品知识】\n"
        "官方预设服务商（助手设置下拉，不含 DeepSeek 独立预设）：\n"
        + "\n".join(preset_lines)
        + "\n\n【当前用户配置（只读，勿输出或索要 API Key）】\n"
        + "\n".join(user_ctx)
        + troubleshooting
    )


def build_system_prompt(config) -> str:
    snapshot = current_allowed_config_snapshot(config)
    lines = [f"{k}: {v}" for k, v in snapshot.items()]
    product = build_product_knowledge(config)
    return (
        "你是 DanmuAI 的「AI 管家」：DanmuAI 使用与设置助手。\n"
        "你有两类能力：\n"
        "1) 问答/排障：功能说明、模型与平台、连接失败原因、操作步骤（如为何 DeepSeek 不能选、401 怎么办）。"
        "此类问题只在 reply 中用清晰中文回答，patch 必须为 {}，needs_confirmation 为 false。\n"
        "2) 配置建议：仅当用户明确要调整助手设置里允许的数字/选项项时，才可给出 patch（见下方字段表）。\n"
        "你不能编造 DanmuAI 没有的功能或配置项；不确定时如实说明，并建议用户去「助手设置」测试连接或侧栏「教程」。\n"
        "禁止在 patch 中出现 api_endpoint、api_key、api_mode、model、热键、识图区域、人格、自定义模型；"
        "若用户要改这些，只在 reply 中指引去「助手设置」或「自定义模型」手动修改。\n"
        "禁止要求用户发送或粘贴 API Key。\n"
        "不确定如何改允许字段时：只解释，不要给 patch。\n"
        "涉及 memory_mode=strong、大幅改变 normal_reply_count 等时请设置 needs_confirmation 为 true。\n"
        f"\n{product}\n"
        f"{_FIELD_CATALOG}\n"
        "当前允许通过 patch 修改的配置快照：\n"
        + "\n".join(lines)
        + "\n\n你必须只输出一个 JSON 对象，不要用 Markdown 代码块包裹整个回复，格式：\n"
        '{"reply":"给用户看的自然语言（可多行）","patch":{"字段":"字符串值"},'
        '"reasons":{"字段":"修改原因"},"needs_confirmation":true}\n'
        "纯问答/排障时 patch 为 {}；有 patch 时 needs_confirmation 应为 true。"
    )


def parse_butler_response(raw_text: str) -> ButlerParseResult:
    text = (raw_text or "").strip()
    if not text:
        return ButlerParseResult(
            reply="AI 未返回内容，请重试。",
            patch={},
            reasons={},
            needs_confirmation=False,
        )

    parsed = _try_parse_json_object(text)
    if parsed is None:
        match = _JSON_BLOCK_RE.search(text)
        if match:
            parsed = _try_parse_json_object(match.group(1).strip())

    if not isinstance(parsed, dict):
        return ButlerParseResult(
            reply=text[:4000] if text else "AI 返回格式无法解析，请换个说法重试。",
            patch={},
            reasons={},
            needs_confirmation=False,
        )

    reply = str(parsed.get("reply") or "").strip()
    if not reply:
        reply = "已处理你的请求。"

    patch_raw = parsed.get("patch")
    patch: dict[str, str] = {}
    if isinstance(patch_raw, dict):
        for key, value in patch_raw.items():
            if value is None:
                continue
            patch[str(key)] = str(value).strip()

    reasons_raw = parsed.get("reasons")
    reasons: dict[str, str] = {}
    if isinstance(reasons_raw, dict):
        for key, value in reasons_raw.items():
            if value is None:
                continue
            reasons[str(key)] = str(value).strip()

    needs_confirmation = bool(parsed.get("needs_confirmation", False))
    if patch and not needs_confirmation:
        needs_confirmation = True

    return ButlerParseResult(
        reply=reply,
        patch=patch,
        reasons=reasons,
        needs_confirmation=needs_confirmation,
    )


def sanitize_patch(
    patch: dict[str, str],
    reasons: dict[str, str],
    config,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    discarded: list[str] = []
    filtered: dict[str, str] = {}
    filtered_reasons: dict[str, str] = {}

    for key, value in patch.items():
        if key not in AI_BUTLER_ALLOWED_KEYS:
            discarded.append(key)
            continue
        filtered[key] = value
        if key in reasons:
            filtered_reasons[key] = reasons[key]

    if filtered:
        normalized = normalize_butler_patch_items(filtered, config)
        filtered = normalized
        filtered_reasons = {k: filtered_reasons[k] for k in filtered if k in filtered_reasons}

    return filtered, filtered_reasons, discarded


def normalize_butler_patch_items(items: dict[str, str], config) -> dict[str, str]:
    """内存校验/归一化，不写库；规则与 ConfigService._normalize_items 对齐。"""
    out = {k: str(v) for k, v in items.items()}

    if "danmu_max_chars" in out:
        from app.danmu_engine import DANMU_MAX_CHARS_MAX, DANMU_MAX_CHARS_MIN

        try:
            value = int(out["danmu_max_chars"])
            out["danmu_max_chars"] = str(max(DANMU_MAX_CHARS_MIN, min(value, DANMU_MAX_CHARS_MAX)))
        except (TypeError, ValueError):
            out["danmu_max_chars"] = config_value_with_default(config, "danmu_max_chars")

    if "danmu_lines" in out:
        from app.danmu_engine import DEFAULT_DANMU_LINES, clamp_danmu_lines

        try:
            out["danmu_lines"] = str(clamp_danmu_lines(int(out["danmu_lines"])))
        except (TypeError, ValueError):
            out["danmu_lines"] = str(DEFAULT_DANMU_LINES)

    if "layout_mode" in out:
        from app.danmu_engine import normalize_layout_mode

        out["layout_mode"] = normalize_layout_mode(out["layout_mode"])

    _clamp_int_key(out, "opacity", 100, 0, 100)

    if "normal_recognition_interval_sec" in out or "normal_reply_count" in out:
        from app.personae import DEFAULT_NORMAL_REPLY_COUNT

        _clamp_int_key(out, "normal_recognition_interval_sec", 5, 1, 60)
        _clamp_int_key(out, "normal_reply_count", DEFAULT_NORMAL_REPLY_COUNT, 1, 20)

    if "memory_mode" in out or "memory_window" in out:
        _clamp_choice(
            out,
            "memory_mode",
            ("off", "dedup_only", "scene_card", "strong"),
            "off",
        )
        _clamp_int_key(out, "memory_window", 10, 1, 20)

    if "eviction_mode" in out:
        _clamp_choice(out, "eviction_mode", ("natural", "accelerate"), "natural")

    if "empty_accel" in out:
        raw = out["empty_accel"].strip().lower()
        out["empty_accel"] = "1" if raw in ("1", "true", "yes", "on") else "0"

    if "temperature" in out:
        try:
            temp = float(out["temperature"])
            temp = max(0.0, min(2.0, temp))
            out["temperature"] = str(temp)
        except (TypeError, ValueError):
            out["temperature"] = config_value_with_default(config, "temperature")

    if "danmu_speed" in out:
        try:
            speed = float(out["danmu_speed"])
            speed = max(0.5, min(5.0, speed))
            out["danmu_speed"] = str(speed)
        except (TypeError, ValueError):
            out["danmu_speed"] = config_value_with_default(config, "danmu_speed")

    if "dedup_threshold" in out:
        try:
            thr = float(out["dedup_threshold"])
            thr = max(0.0, min(1.0, thr))
            out["dedup_threshold"] = str(thr)
        except (TypeError, ValueError):
            out["dedup_threshold"] = config_value_with_default(config, "dedup_threshold")

    if "font_size" in out:
        _clamp_int_key(out, "font_size", 24, 12, 72)

    if "max_tokens" in out:
        _clamp_int_key(out, "max_tokens", 512, 1, 8192)

    if "image_max_width" in out:
        _clamp_int_key(out, "image_max_width", 768, 256, 1920)

    if "image_quality" in out:
        _clamp_int_key(out, "image_quality", 85, 1, 100)

    return out


def chat(app: "DanmuApp", message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    user_message = (message or "").strip()
    if not user_message:
        raise ValueError("请输入消息内容。")

    config = app.config
    endpoint, api_key, model, mode = ensure_api_configured(config)
    system_pt = build_system_prompt(config)
    turns = _normalize_history(history)

    raw = _call_provider(
        endpoint,
        api_key,
        model,
        mode,
        system_pt,
        user_message,
        turns,
        temperature=min(config.get_float("temperature", 0.7), 0.6),
    )

    parsed = parse_butler_response(raw)
    filtered_patch, filtered_reasons, discarded = sanitize_patch(
        parsed.patch, parsed.reasons, config
    )
    current_values = {
        key: current_allowed_config_snapshot(config).get(key, "")
        for key in filtered_patch
    }

    return {
        "reply": parsed.reply,
        "patch": filtered_patch,
        "reasons": filtered_reasons,
        "needs_confirmation": parsed.needs_confirmation if filtered_patch else False,
        "current_values": current_values,
        "discarded_fields": discarded,
    }


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not history:
        return []
    out: list[dict[str, str]] = []
    for item in history[-BUTLER_HISTORY_MAX_TURNS * 2 :]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip().lower()
        if role not in ("user", "assistant"):
            role = "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out[-BUTLER_HISTORY_MAX_TURNS * 2 :]


def _call_provider(
    endpoint: str,
    api_key: str,
    model: str,
    mode: str,
    system_pt: str,
    user_message: str,
    history: list[dict[str, str]],
    *,
    temperature: float,
) -> str:
    transport = resolve_api_transport(endpoint, mode)
    timeout = httpx.Timeout(60.0, connect=10.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            if transport == "doubao":
                return _chat_doubao(
                    client, endpoint, api_key, model, system_pt, user_message, history, temperature
                )
            return _chat_openai(
                client, endpoint, api_key, model, mode, system_pt, user_message, history, temperature
            )
    except httpx.TimeoutException as exc:
        raise ValueError(tr("ai.error_timeout")) from exc
    except httpx.HTTPStatusError as exc:
        raise ValueError(format_http_status_error(exc)) from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(tr("ai.error_request_failed").format(error=exc)) from exc


def _chat_doubao(
    client: httpx.Client,
    endpoint: str,
    api_key: str,
    model: str,
    system_pt: str,
    user_message: str,
    history: list[dict[str, str]],
    temperature: float,
) -> str:
    input_messages: list[dict[str, Any]] = []
    for turn in history:
        role = turn["role"]
        text = turn["content"]
        if role == "assistant":
            input_messages.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            )
        else:
            input_messages.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                }
            )
    input_messages.append(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": user_message}],
        }
    )

    data: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "stream": False,
        "max_output_tokens": BUTLER_MAX_OUTPUT_TOKENS,
        "thinking": dict(THINKING_DISABLED),
        "temperature": temperature,
    }
    if system_pt:
        data["instructions"] = system_pt

    url = f"{endpoint.rstrip('/')}/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = client.post(url, headers=headers, json=data)
    resp.raise_for_status()
    body = resp.json()
    text = extract_text_from_response(body)
    if text:
        return text.strip()
    raise ValueError(tr("ai.error_empty_response"))


def _chat_openai(
    client: httpx.Client,
    endpoint: str,
    api_key: str,
    model: str,
    mode: str,
    system_pt: str,
    user_message: str,
    history: list[dict[str, str]],
    temperature: float,
) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_pt}]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    caps = get_capabilities_for_endpoint(endpoint, mode)
    adapter = get_openai_adapter(endpoint, mode)
    data: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    adapter.patch_openai_chat_body(data, max_tokens=BUTLER_MAX_OUTPUT_TOKENS, caps=caps)

    url = f"{endpoint.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = client.post(url, headers=headers, json=data)
    resp.raise_for_status()
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError(tr("ai.error_empty_response"))
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
        joined = "".join(parts).strip()
        if joined:
            return joined
    raise ValueError(tr("ai.error_empty_response"))


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
