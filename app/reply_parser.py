"""AI 回复解析：多格式容错、标准化批次与本地弹幕池补齐。

支持三种输入格式（按检测顺序）：
  1. JSON 数组 — 直接作为弹幕列表
  2. JSON 对象 — comments/replies/items/data 键，或 scene_memory 信封（含 memory 更新）
  3. 纯文本 — 按换行拆分

畸形 JSON 容错：流式截断导致 ``][`` 拼接时，只解析第一个完整数组段。

normalize_reply_batch 将 AI 条数补齐到 scene_count + filler_count：
  先取 AI 原文去重，不足时用本地池（danmu_pool_zh.json）或内置 i18n 占位句轮换填充。
  上屏截断在 danmu_engine.normalize_danmu_display_text（中文默认 15 字 / 英文 40 字符 + ``...``）。

调用方：DanmuApp._on_ai_reply() → parse_ai_reply_with_memory → normalize_reply_batch
"""
from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

from app.danmu_pool import load_danmu_pool_for_config, sample_danmu_for_config
from app.translations import tr

if TYPE_CHECKING:
    from app.memory.types import VisualMemoryUpdate

_LEGACY_SCENE_FILLERS = (
    "reply.scene_filler_1",
    "reply.scene_filler_2",
)
_LEGACY_GENERIC_FILLERS = (
    "reply.generic_filler_1",
    "reply.generic_filler_2",
    "reply.generic_filler_3",
)


def _legacy_scene_fillers() -> list[str]:
    return [tr(key) for key in _LEGACY_SCENE_FILLERS]


def _legacy_generic_fillers() -> list[str]:
    return [tr(key) for key in _LEGACY_GENERIC_FILLERS]


def _scene_fillers(config=None) -> list[str]:
    pool = load_danmu_pool_for_config(config)
    if pool:
        return sample_danmu_for_config(config, min(32, len(pool)), rng=random)
    return _legacy_scene_fillers()


def _generic_fillers(config=None) -> list[str]:
    pool = load_danmu_pool_for_config(config)
    if pool:
        return sample_danmu_for_config(config, min(48, len(pool)), rng=random)
    return _legacy_generic_fillers()


def _try_parse_json_array(raw: str):
    """解析 JSON 数组；遇 ``][`` 拼接（流式截断）时只取第一段 ``[...]``。"""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return parsed
    if "][" in raw:
        head = raw.split("][", 1)[0] + "]"
        try:
            parsed = json.loads(head)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return parsed
    return None


def parse_ai_reply_with_memory(
    text: str,
    scene_generation: int = 0,
) -> tuple[list[str], VisualMemoryUpdate | None]:
    """解析 AI 原始文本为弹幕列表，并提取可选的 scene_memory 视觉记忆更新。

    返回 (normalized_comments, memory_update)；无记忆块时 memory_update 为 None。
    scene_generation 用于回填信封内未带代际的记忆条目。
    """
    from app.memory.visual_update import (
        extract_comments_from_envelope,
        parse_scene_memory_envelope,
        visual_update_from_dict,
    )

    raw = str(text or "").strip()
    if not raw:
        return [], None

    parsed = None
    memory_update: VisualMemoryUpdate | None = None

    # 格式分支：数组 → 对象（多键或信封）→ 否则按行文本
    if raw.startswith("[") or raw.startswith("{"):
        if raw.startswith("["):
            parsed = _try_parse_json_array(raw)
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None

    if isinstance(parsed, dict):
        envelope_comments = extract_comments_from_envelope(parsed)
        if envelope_comments is not None:
            candidates = envelope_comments
        else:
            for key in ("comments", "replies", "items", "data"):
                value = parsed.get(key)
                if isinstance(value, list):
                    candidates = value
                    break
            else:
                candidates = []
        memory_update = parse_scene_memory_envelope(parsed)
        if memory_update is None and isinstance(parsed.get("scene_memory"), dict):
            memory_update = visual_update_from_dict(parsed["scene_memory"], scene_generation)
        if memory_update is not None and memory_update.scene_generation <= 0:
            memory_update.scene_generation = scene_generation
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        candidates = [
            part.strip(" -\t\r\n")
            for part in raw.replace("\r", "\n").split("\n")
            if part.strip()
        ]

    normalized: list[str] = []
    for item in candidates:
        value = str(item).strip().strip('"').strip("'")
        if value:
            normalized.append(value)
    return normalized, memory_update


def parse_ai_reply_payload(text: str) -> list[str]:
    """仅解析弹幕列表，忽略 scene_memory（测试与无记忆路径用）。"""
    items, _ = parse_ai_reply_with_memory(text)
    return items


def _append_next_unique_from_pool(
    result: list[str],
    seen: set[str],
    pool: list[str],
    cursor: list[int],
) -> bool:
    """Rotate pool once; append one unseen phrase. False if pool has no new phrase."""
    if not pool:
        return False
    n = len(pool)
    for _ in range(n):
        text = pool[cursor[0] % n]
        cursor[0] += 1
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
        return True
    return False


def normalize_reply_batch(
    items: list[str],
    scene_count: int = 2,
    filler_count: int = 3,
    *,
    allow_shortfall: bool = False,
    config=None,
) -> list[str]:
    """将 AI 回复标准化为固定条数：前 scene_count 条视为场景相关，其余为填充条。

    allow_shortfall=False（默认）：池用尽前尽量凑满 scene_count + filler_count。
    allow_shortfall=True：池无新句时提前结束，用于本地 fallback 等可接受短批次的场景。

    scene_count / filler_count 由 DanmuApp._sync_reply_batch_config 从 normal_reply_count 派生；
    与 parse_ai_reply_with_memory 返回的 memory_update 无关（记忆更新在 _on_ai_reply 单独处理）。
    """
    scene_count = max(1, int(scene_count))
    filler_count = int(filler_count)
    if filler_count <= 0:
        desired_count = scene_count
    else:
        filler_count = max(1, filler_count)
        desired_count = scene_count + filler_count

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)

    result = cleaned[:desired_count]
    scene_fillers = _scene_fillers(config)
    generic_fillers = _generic_fillers(config)

    if allow_shortfall:
        seen = set(result)
        scene_cursor = [0]
        while len(result) < min(scene_count, desired_count):
            if not _append_next_unique_from_pool(result, seen, scene_fillers, scene_cursor):
                break
        generic_cursor = [0]
        while len(result) < desired_count:
            if not _append_next_unique_from_pool(result, seen, generic_fillers, generic_cursor):
                break
        return result

    if filler_count > 0:
        while len(result) < min(scene_count, desired_count):
            pool_index = min(len(result), len(scene_fillers) - 1)
            result.append(scene_fillers[pool_index])
    while len(result) < desired_count:
        filler_index = max(0, len(result) - scene_count) if filler_count > 0 else len(result)
        pool_index = min(filler_index, len(generic_fillers) - 1)
        result.append(generic_fillers[pool_index])
    return result[:desired_count]
