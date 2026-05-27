# Contributing — architecture boundaries

Rules for code changes that touch orchestration, Web API, or runtime state. For day-to-day setup and tests, see [CONTRIBUTING.md](../CONTRIBUTING.md). For agent-specific shortcuts, see [AGENTS.md](../AGENTS.md).

## Before you change high-risk code

Read:

1. [ARCHITECTURE.md](ARCHITECTURE.md)
2. [MAIN_PIPELINE.md](MAIN_PIPELINE.md)
3. [RUNTIME_STATE.md](RUNTIME_STATE.md)
4. [BOUNDARY_GUARD.md](BOUNDARY_GUARD.md)

If you touch scheduling or RTT: [archive/architecture-phases/phase4-freeze.md](archive/architecture-phases/phase4-freeze.md).

## Where to implement features

| Feature type | Location |
|--------------|----------|
| Web UI, settings, new REST | `web/static/`, `app/web_api/routes.py` |
| Personas / templates / models | `app/web_api/`, existing managers |
| Overlay appearance / tracks | `app/overlay.py`, `app/danmu_engine.py` |
| Capture / AI / queue timing | `main.py` — **avoid** unless necessary |

## Web / API rules

**Do not** add in `app/web_console.py` or `app/web_api/*`:

- `danmu_app._…`, `app._…`, `ai_worker._…`
- `_mic_service`, `_set_error_status_safe`, `_build_live_status_snapshot`, `_visible_display_count`, `_resolve_request_credentials`
- Direct reads of `_last_api_trigger_at`, `_request_started_at_by_id`, `_rtt_history`
- `danmu_app.web_runtime_state` / `cached_danmu_lines` / `cached_layout_mode` for status

**Do** use public facades:

- `build_status_snapshot()`, `build_diagnostic_snapshot()`
- `apply_web_config_payload()`, `set_active_personae()`, `resolve_request_credentials()`
- `run_mic_test()`, `set_web_error_status()`, `start()`, `stop()`, `toggle()`
- `request_capture_region_selection()`, `reset_capture_region()`, `get_capture_region_status()`

If a façade is missing, add it on `DanmuApp` first, then call it from Web.

Temporary exception (must include comment):

```python
TODO(phase2-boundary): reason=..., current_private_access=..., target_public_api=...
```

## Main pipeline

Protected call chain (do not reorder or bypass casually):

- `_on_screenshot_timer()` → `_on_normal_capture_tick()` → `_capture_screenshot()` → `_trigger_api_call()`
- `_on_ai_reply()` → `_enqueue_reply_batch()` → `_consume_reply_queue()`

Adding `QTimer`, `QThreadPool.globalInstance().start`, `threading.Thread`, or `asyncio.create_task` requires updating [main-pipeline-sequence.md](main-pipeline-sequence.md) in the **same commit**.

## Runtime fields

- New `self._field` in `DanmuApp.__init__` → register in [runtime-state-map.md](runtime-state-map.md).
- New Web-visible state → extend `StatusSnapshotBuilder`, not ad-hoc dict assembly in routes.
- Do not write `danmu_count`, `_total_*_tokens`, `_start_time`, `_web_error_*`, `_cached_danmu_*` directly on `DanmuApp` (owned by `StatsState` / `WebRuntimeState`).

## Scheduling and timing (frozen)

- Use `RequestScheduler` for trigger gating and `last_api_trigger_at`.
- Use `RequestTimingService` for RTT / `request_started_at_by_id`.
- Do not add parallel throttle fields on `DanmuApp`.
- Tests: `python -m pytest tests/test_request_scheduling.py -q`

## Do not migrate (without explicit project decision)

- `reply_buffer`, `ai_in_flight`, `_latest_screenshot`, `_scene_generation`
- Splitting `DanmuEngine` / `Overlay` or rewriting `_trigger_api_call` / `_consume_reply_queue`
- Large storage repository split

## Storage

- `config.conn` only in: `config_store`, `history`, `history_writer`, `templates`, `danmu_engine` (whitelist enforced by Boundary Guard).
- No new schema changes without migration plan and docs.

## `DanmuEngine` / `Overlay`

- Engine may use overlay for measure/pixmap and SQLite for dedup warmup—do not add more UI or Web imports into engine.
- Do not refactor engine/overlay coupling in drive-by PRs.

## Pre-submit checklist

```bash
python scripts/boundary_guard.py
python -m pytest tests/test_request_scheduling.py tests/test_boundary_guard.py -q
# broader:
python -m pytest tests/ -q
```

Manual checks:

- [ ] No new `._` access under `app/web_api` or `web_console`
- [ ] `runtime-state-map.md` updated if `DanmuApp` fields added
- [ ] `main-pipeline-sequence.md` updated if timers/threads added
- [ ] `docs/CHANGELOG.md` for user-visible behavior
- [ ] `docs/WEB_CONSOLE.md` if API/UI changed

## Historical phase documents

Detailed phase plans live under [archive/architecture-phases/](archive/architecture-phases/). Use them for context, not as the primary onboarding path.
