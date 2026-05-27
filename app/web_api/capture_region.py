"""识图区域 Web 业务 façade：读写 region_*，不触碰 Qt 或截图链路。"""
from __future__ import annotations

from typing import Any

from app.region_selector import normalize_region_for_screen

SELECTION_IDLE = "idle"
SELECTION_SELECTING = "selecting"
SELECTION_SAVED = "saved"
SELECTION_CANCELLED = "cancelled"
SELECTION_INVALID = "invalid"


def capture_region_mode(config) -> str:
    """Return ``full`` or ``custom`` based on stored region."""
    _x, _y, w, h = config.get_region()
    if w > 0 and h > 0:
        return "custom"
    return "full"


def read_capture_region_status(config, selection_state: str = SELECTION_IDLE) -> dict[str, Any]:
    x, y, w, h = config.get_region()
    return {
        "mode": capture_region_mode(config),
        "region": {"x": x, "y": y, "w": w, "h": h},
        "selection_state": selection_state,
    }


def clear_capture_region(config) -> None:
    config.set_region(0, 0, 0, 0)


def apply_capture_region(
    config,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int, int, int] | None:
    """Normalize and persist screen-relative region; return None if invalid."""
    normalized = normalize_region_for_screen(
        x, y, w, h, screen_width, screen_height
    )
    if normalized is None:
        return None
    nx, ny, nw, nh = normalized
    config.set_region(nx, ny, nw, nh)
    return normalized
