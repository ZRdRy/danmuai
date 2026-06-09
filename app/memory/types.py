"""Types and helpers for scene brief + prompt dedup memory."""

from __future__ import annotations

from dataclasses import dataclass

MAX_BULLET_SNIPPET_LEN = 15
DEFAULT_PROMPT_DEDUP_WINDOW = 10
PROMPT_DEDUP_WINDOW_MIN = 1
PROMPT_DEDUP_WINDOW_MAX = 20

SCENE_BRIEF_MAX_LEN_ZH = 20
SCENE_BRIEF_MAX_LEN_EN = 40
SCENE_MEMORY_INTERVAL_MULTIPLIER_MAX = 12
DEFAULT_SCENE_MEMORY_INTERVAL_SEC = 5


def snap_scene_memory_interval_sec(interval_sec: int, recognition_sec: int) -> int:
    """Snap interval to the nearest multiple of recognition_sec (min 1x, max 12x)."""
    recognition_sec = max(1, int(recognition_sec))
    try:
        interval_sec = int(interval_sec)
    except (TypeError, ValueError):
        interval_sec = recognition_sec
    multiplier = max(1, (interval_sec + recognition_sec - 1) // recognition_sec)
    multiplier = min(multiplier, SCENE_MEMORY_INTERVAL_MULTIPLIER_MAX)
    return multiplier * recognition_sec


def scene_memory_interval_from_config(config) -> int:
    recognition = max(1, config.get_int("normal_recognition_interval_sec", 5))
    raw = config.get_int("scene_memory_interval_sec", recognition)
    return snap_scene_memory_interval_sec(raw, recognition)


def scene_memory_tick_multiplier(config) -> int:
    recognition = max(1, config.get_int("normal_recognition_interval_sec", 5))
    interval = scene_memory_interval_from_config(config)
    return max(1, interval // recognition)


def clamp_prompt_dedup_window(
    raw: int | str | None,
    *,
    default: int = DEFAULT_PROMPT_DEDUP_WINDOW,
) -> int:
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(PROMPT_DEDUP_WINDOW_MIN, min(value, PROMPT_DEDUP_WINDOW_MAX))


def prompt_dedup_window_from_config(config) -> int:
    """Internal window size; legacy memory_window key still honored if present."""
    return clamp_prompt_dedup_window(
        config.get("memory_window", ""),
        default=DEFAULT_PROMPT_DEDUP_WINDOW,
    )


def bullet_angle_from_index(content_index: int, scene_count: int) -> str:
    if content_index < scene_count:
        return f"scene_{content_index}"
    return f"filler_{content_index - scene_count}"


def truncate_scene_brief(text: str, *, lang: str = "zh") -> str:
    from app.translations import Translator

    effective_lang = lang or Translator.get_language()
    max_len = (
        SCENE_BRIEF_MAX_LEN_EN
        if effective_lang == "en"
        else SCENE_BRIEF_MAX_LEN_ZH
    )
    cleaned = (text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len]


@dataclass
class DisplayedBullet:
    text: str
    angle: str = ""
    recorded_at: float = 0.0
