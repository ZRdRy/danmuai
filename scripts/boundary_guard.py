"""Backward-compatible CLI entry: python scripts/boundary_guard.py"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.boundary_guard.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
