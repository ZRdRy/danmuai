from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable


def _run_git(repo_root: Path, *args: str, check: bool=True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', *args], cwd=repo_root, check=check, capture_output=True, text=True, encoding='utf-8')

def _repo_has_head(repo_root: Path) -> bool:
    try:
        _run_git(repo_root, 'rev-parse', '--verify', 'HEAD')
        return True
    except subprocess.CalledProcessError:
        return False

def _normalize_rel(path_str: str) -> Path:
    return Path(path_str.replace('\\', '/'))

def get_changed_files(repo_root: Path) -> dict[Path, str]:
    result = _run_git(repo_root, 'status', '--porcelain=v1', '--untracked-files=all')
    changed: dict[Path, str] = {}
    for raw in result.stdout.splitlines():
        if not raw.strip():
            continue
        status = raw[:2]
        path_part = raw[3:]
        if '->' in path_part:
            path_part = path_part.split('->', 1)[1].strip()
        changed[_normalize_rel(path_part)] = status
    return changed

def _parse_added_lines_from_diff(diff_text: str) -> list[tuple[int, str]]:
    added: list[tuple[int, str]] = []
    current_line: int | None = None
    for raw in diff_text.splitlines():
        if raw.startswith('@@'):
            match = re.search('\\+(\\d+)(?:,(\\d+))?', raw)
            if not match:
                current_line = None
                continue
            current_line = int(match.group(1))
            continue
        if current_line is None:
            continue
        if raw.startswith('+++'):
            continue
        if raw.startswith('+'):
            added.append((current_line, raw[1:]))
            current_line += 1
        elif raw.startswith('-'):
            continue
        else:
            current_line += 1
    return added

def get_added_lines(repo_root: Path, rel_path: Path, status: str) -> list[tuple[int, str]]:
    abs_path = repo_root / rel_path
    if status == '??' or not _repo_has_head(repo_root):
        lines = abs_path.read_text(encoding='utf-8').splitlines()
        return [(idx + 1, line) for idx, line in enumerate(lines)]
    diff = _run_git(repo_root, 'diff', '--no-color', '--unified=0', 'HEAD', '--', str(rel_path), check=False)
    if diff.returncode not in (0, 1):
        raise RuntimeError(diff.stderr.strip() or f'git diff failed for {rel_path}')
    return _parse_added_lines_from_diff(diff.stdout)

def _iter_python_files(root: Path) -> Iterable[Path]:
    yield from root.rglob('*.py')

def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding='utf-8').splitlines()

def _has_phase2_todo(lines: list[str], line_no: int) -> bool:
    start = max(0, line_no - 3)
    end = min(len(lines), line_no)
    for idx in range(start, end):
        if 'TODO(phase2-boundary)' in lines[idx]:
            return True
    return False

def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith('#')
