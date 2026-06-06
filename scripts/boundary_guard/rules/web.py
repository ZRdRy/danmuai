from __future__ import annotations

import re
from pathlib import Path

from ..constants import (
    DIAGNOSTICS_ROUTE_FORBIDDEN_CALLS,
    DIAGNOSTICS_ROUTE_FORBIDDEN_TOKENS,
    WEB_API_DIR,
    WEB_CONSOLE_PATH,
    WEB_DIAGNOSTICS_UI_FORBIDDEN_PATTERNS,
    WEB_PRIVATE_PATTERNS,
    WEB_STATIC_DIR,
)
from ..git_diff import (
    _has_phase2_todo,
    _is_comment_or_blank,
    _read_lines,
    get_added_lines,
)
from ..models import Finding
from ..source_parse import _extract_function_body, _meaningful_body_lines


def check_web_private_access(repo_root: Path, changed: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    targets = [WEB_CONSOLE_PATH]
    targets.extend(sorted((path.relative_to(repo_root) for path in (repo_root / WEB_API_DIR).glob('*.py'))))
    for rel_path in targets:
        if rel_path not in changed:
            continue
        lines = _read_lines(repo_root / rel_path)
        for line_no, line in get_added_lines(repo_root, rel_path, changed[rel_path]):
            if _is_comment_or_blank(line):
                continue
            for pattern, message in WEB_PRIVATE_PATTERNS:
                if re.search(pattern, line):
                    if _has_phase2_todo(lines, line_no):
                        break
                    findings.append(Finding(severity='error', rule='phase1-boundary-rules.md 2.1 / 2.3', path=str(rel_path), line=line_no, message=message))
                    break
    return findings

def check_web_status_composition(repo_root: Path, changed: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    if WEB_CONSOLE_PATH not in changed:
        return findings
    lines = _read_lines(repo_root / WEB_CONSOLE_PATH)
    body = _extract_function_body(lines, 'refresh_status')
    if not body:
        return findings
    body_text = '\n'.join(body)
    if 'build_status_snapshot(' not in body_text:
        findings.append(Finding(severity='error', rule='phase1-boundary-rules.md 3.2 / 3.3', path=str(WEB_CONSOLE_PATH), line=0, message='`WebConsoleBridge.refresh_status()` 必须委托 `build_status_snapshot()`，禁止 Web 层自行拼接运行态状态'))
    return findings

def check_status_route_boundary(repo_root: Path, changed: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    if WEB_CONSOLE_PATH not in changed:
        return findings
    lines = _read_lines(repo_root / WEB_CONSOLE_PATH)
    body = _extract_function_body(lines, 'status')
    body_text = '\n'.join(_meaningful_body_lines(body))
    if not body_text:
        return findings
    if 'build_diagnostic_snapshot(' in body_text or '"diagnostics"' in body_text or "'diagnostics'" in body_text:
        findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-c', path=str(WEB_CONSOLE_PATH), line=0, message='`/api/status` must not be polluted by diagnostics data or `build_diagnostic_snapshot()`'))
    return findings

def check_web_diagnostics_route_boundary(repo_root: Path, changed: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    routes_path = WEB_API_DIR / 'routes.py'
    if routes_path not in changed:
        return findings
    lines = _read_lines(repo_root / routes_path)
    routes_text = '\n'.join(lines)
    if '"/api/diagnostics"' not in routes_text and "'/api/diagnostics'" not in routes_text:
        return findings
    body = _extract_function_body(lines, 'get_diagnostics')
    meaningful = _meaningful_body_lines(body)
    body_text = '\n'.join(meaningful)
    if not body or 'build_diagnostic_snapshot(' not in body_text:
        findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-b', path=str(routes_path), line=0, message='`/api/diagnostics` must delegate to `DanmuApp.build_diagnostic_snapshot()`'))
    if 'build_status_snapshot(' in body_text:
        findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-b', path=str(routes_path), line=0, message='`/api/diagnostics` must stay independent from `/api/status` and must not reuse `build_status_snapshot()`'))
    if '"ok": True' not in body_text and "'ok': True" not in body_text:
        findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-b', path=str(routes_path), line=0, message='`/api/diagnostics` must return an independent payload with `ok` and `diagnostics` keys'))
    for line_no, line in get_added_lines(repo_root, routes_path, changed[routes_path]):
        if _is_comment_or_blank(line):
            continue
        for pattern, message in DIAGNOSTICS_ROUTE_FORBIDDEN_TOKENS:
            if re.search(pattern, line):
                findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-b', path=str(routes_path), line=line_no, message=message))
                break
        else:
            for token in DIAGNOSTICS_ROUTE_FORBIDDEN_CALLS:
                if token in line:
                    findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-b', path=str(routes_path), line=line_no, message='Diagnostics route must not call trigger, reply, or queue pipeline functions'))
                    break
    return findings

def check_web_diagnostics_ui_boundary(repo_root: Path, changed: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    targets = (WEB_STATIC_DIR / 'app.js', WEB_STATIC_DIR / 'index.html')
    for rel_path in targets:
        if rel_path not in changed:
            continue
        for line_no, line in get_added_lines(repo_root, rel_path, changed[rel_path]):
            if _is_comment_or_blank(line):
                continue
            for pattern, message in WEB_DIAGNOSTICS_UI_FORBIDDEN_PATTERNS:
                if re.search(pattern, line):
                    findings.append(Finding(severity='error', rule='diagnostics-plan.md / phase5-c', path=str(rel_path), line=line_no, message=message))
                    break
    return findings
