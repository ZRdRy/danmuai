from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    line: int
    message: str
