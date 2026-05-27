"""Architecture-round acceptance: in-process boundary guard on repository root."""

from __future__ import annotations

from pathlib import Path

from scripts.boundary_guard import format_findings, run_boundary_guard


def test_boundary_guard_passes_on_repository_root() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    findings = run_boundary_guard(repo_root)
    assert findings == [], format_findings(findings)
