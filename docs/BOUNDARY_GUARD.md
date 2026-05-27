# Boundary Guard

`Boundary Guard` automates architecture rules from [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md). It is **not** a general linter—it scans **git-changed** lines for DanmuAI-specific regressions.

Script: [scripts/boundary_guard.py](../scripts/boundary_guard.py)

## Run

From repository root:

```bash
python scripts/boundary_guard.py
```

From another directory:

```bash
python scripts/boundary_guard.py --repo-root /path/to/danmu
```

Success: `Boundary Guard: PASS` (exit 0).  
Failure: `Boundary Guard: FAIL` with file/line details (exit 1).

Also run via [scripts/run_acceptance_gates.py](../scripts/run_acceptance_gates.py) and `tests/test_boundary_guard.py`.

## What it checks

| Area | Rule |
|------|------|
| Web/API | No new private `danmu_app._` / `app._` / `ai_worker._` access; no bypass of `build_status_snapshot()` |
| Config | No `config.conn` outside whitelist modules |
| Timers/threads | New `QTimer` / `QThreadPool` / `threading.Thread` / `asyncio.create_task` requires `docs/main-pipeline-sequence.md` changed in same diff |
| Runtime fields | New `DanmuApp.__init__` fields must appear in `docs/runtime-state-map.md` |
| Status | `build_status_snapshot()` must delegate to `StatusSnapshotBuilder` |
| Config path | `apply_web_config_payload()` must use `ConfigService` |
| Custom models | Default model changes must use `set_default_model_selection()` |
| Generation pipeline | `GenerationPipelineState` read-only; no Qt/pipeline calls |
| Request services | `RequestScheduler` / `RequestTimingService` boundaries (no Qt, no queue/overlay) |
| Diagnostics | `DiagnosticSnapshotBuilder` read-only; `/api/diagnostics` separate from status |
| Baseline file | `docs/final-architecture-baseline.md` must exist |

## Temporary exceptions

```python
TODO(phase2-boundary): reason=..., current_private_access=..., target_public_api=...
```

Only lines near this comment may pass private-access checks.

## When to run

- Before PRs touching `main.py`, `app/web_console.py`, `app/web_api/`, or `app/application/`
- After adding timers, runtime fields, or Web status fields

## Read first

| Change | Documents |
|--------|-----------|
| Web/API | [WEB_CONSOLE.md](WEB_CONSOLE.md), [RUNTIME_STATE.md](RUNTIME_STATE.md) |
| Pipeline | [MAIN_PIPELINE.md](MAIN_PIPELINE.md), [main-pipeline-sequence.md](main-pipeline-sequence.md) |
| New field | [runtime-state-map.md](runtime-state-map.md) |

## Phase guard history

Older incremental guard notes (Phase 3–5) are in [archive/architecture-phases/](archive/architecture-phases/) and in git history. This file describes the **current** script behavior.

## Related

- [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md)
- [final-architecture-baseline.md](final-architecture-baseline.md) — short baseline pointer
