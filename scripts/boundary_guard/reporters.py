from __future__ import annotations

from .models import Finding


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return 'Boundary Guard: PASS'
    lines = ['Boundary Guard: FAIL']
    for finding in findings:
        location = f'{finding.path}:{finding.line}' if finding.line > 0 else finding.path
        lines.append(f'- [{finding.severity.upper()}] {location} | {finding.rule} | {finding.message}')
    return '\n'.join(lines)
