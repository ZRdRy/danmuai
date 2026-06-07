"""识图区域 Web 业务 façade：读写 region_*，不触碰 Qt 或截图链路。

路由（由 ``app.web_api.routes`` 注册）：
- ``GET /api/capture-region/status``：返回 ``{x, y, w, h, mode}``（mode = full / custom）。
- ``POST /api/capture-region/save``：写入框选区域（屏内相对坐标，**不**是绝对屏幕坐标）；
  经 ``app.region_selector.normalize_region_for_screen`` 钳位。
- ``POST /api/capture-region/cancel``：取消当前选择。

注册方式：``app.web_api.routes`` 调用 ``register_capture_region_routes(app, bridge, check_token)``。
本模块不触碰 Qt 或截图链路；只读写 config.region_* 字段，由 ``app.snipper`` 在截图时读出。
"""
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
