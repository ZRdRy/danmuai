"""Derive pet animation hint from existing DanmuApp runtime (no new RuntimeState fields)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import DanmuApp

VALID_ANIMATIONS = ("idle", "review", "wave", "failed", "run", "jump")
_ONE_SHOT_SEC = 1.5


def resolve_base_animation(app: "DanmuApp") -> str:
    # PET-017: idle is the only resting animation; Agent review/run linkage (PET-007)
    # is intentionally disabled so untouched pets stay on row 0. One-shots and drag
    # interaction still override via resolve_pet_animation_hint / resolve_interaction_animation.
    return "idle"


def resolve_pet_animation_hint(
    app: "DanmuApp",
    *,
    one_shot: str | None = None,
    one_shot_until: float = 0.0,
    now: float | None = None,
) -> str:
    ts = now if now is not None else time.monotonic()
    if one_shot and one_shot in VALID_ANIMATIONS and ts < one_shot_until:
        return one_shot
    return resolve_base_animation(app)
