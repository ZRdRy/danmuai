from __future__ import annotations

import argparse
from pathlib import Path

from .reporters import format_findings
from .runner import run_boundary_guard


def main(argv: list[str] | None=None) -> int:
    parser = argparse.ArgumentParser(description='Boundary guard for Phase 1 architecture rules.')
    parser.add_argument('--repo-root', default='.', help='Repository root to scan. Defaults to current working directory.')
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    findings = run_boundary_guard(repo_root)
    print(format_findings(findings))
    return 1 if findings else 0
