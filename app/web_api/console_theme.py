"""Web 控制台主题偏好：config.db 字符串键，不影响主链路运行态。"""

from __future__ import annotations

from fastapi import HTTPException

CONSOLE_THEME_KEY = "console_theme"
DEFAULT_CONSOLE_THEME = "light"
_VALID_THEMES = frozenset({"light", "dark"})


def normalize_theme(value: object) -> str:
    if isinstance(value, str) and value.strip().lower() == "dark":
        return "dark"
    return DEFAULT_CONSOLE_THEME


def get_from_config(config) -> dict[str, str]:
    raw = config.get(CONSOLE_THEME_KEY, default=DEFAULT_CONSOLE_THEME)
    return {"theme": normalize_theme(raw)}


def save_to_config(config, theme: str) -> None:
    config.set(CONSOLE_THEME_KEY, normalize_theme(theme))


def validate_payload(body: dict) -> str:
    theme = body.get("theme", DEFAULT_CONSOLE_THEME)
    if theme is None:
        theme = DEFAULT_CONSOLE_THEME
    if not isinstance(theme, str):
        raise HTTPException(status_code=400, detail="theme 必须为字符串")
    normalized = theme.strip().lower()
    if normalized not in _VALID_THEMES:
        raise HTTPException(status_code=400, detail="theme 仅允许 light 或 dark")
    return normalized
