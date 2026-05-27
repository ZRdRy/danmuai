# Runtime state

DanmuAI keeps most mutable session data on `DanmuApp` in `main.py`. Newer code **projects** that data for Web and diagnostics instead of letting HTTP handlers read private fields.

## Layers

```text
DanmuApp (owns QTimers, QPixmap, queues, in-flight counts)
    │
    ├─ StatsState              danmu_count, tokens, session start
    ├─ WebRuntimeState         web error text, cached layout/lines for UI
    ├─ RequestScheduler        last_api_trigger_at, schedule block reasons
    ├─ RequestTimingService    request_started_at_by_id, rtt_history
    │
    ├─ RuntimeState.from_app()           read-only aggregate (internal/debug)
    ├─ GenerationPipelineState.from_app() read-only generation fields
    │
    ├─ StatusSnapshotBuilder.build()     → GET /api/status
    └─ DiagnosticSnapshotBuilder.build() → GET /api/diagnostics
```

## Public outputs

### `/api/status`

- Built only through `DanmuApp.build_status_snapshot()` → `StatusSnapshotBuilder`.
- `WebConsoleBridge.refresh_status()` must delegate to that method.
- Must **not** include diagnostics-only fields or call `build_diagnostic_snapshot()`.

### `/api/diagnostics`

- Route: `GET /api/diagnostics` in `app/web_api/routes.py`.
- Must call `build_diagnostic_snapshot()` only.
- Groups typically include scheduler, timing, and read-only runtime projections.
- UI in `web/static/` must not reference `_last_api_trigger_at`, `_request_started_at_by_id`, `_rtt_history`, `reply_buffer`, etc.

## Ownership rules (frozen)

These stay on `DanmuApp` / main-thread orchestration—do not move into `app/application` services:

- `ai_in_flight`, `_pending_request_meta`, `_inflight_screenshot_id`
- `_scene_generation`, `reply_buffer`, `_latest_screenshot` / `_latest_screenshot_id`
- `QTimer`, `QThreadPool`, `QPixmap`, `_mic_service`

These **are** owned by application services:

| Field / concern | Owner |
|-----------------|--------|
| `last_api_trigger_at` | `RequestScheduler` |
| `request_started_at_by_id` (`dict[str, float]`, composite `{round}:{screenshot_id}:{scene_generation}`), `rtt_history` | `RequestTimingService` |
| `danmu_count`, token totals, `_start_time` | `StatsState` |
| Web error + display cache | `WebRuntimeState` |

`DanmuApp` may expose compatibility properties that delegate to services; Boundary Guard blocks new direct writes to migrated fields.

## Adding a new runtime field

1. Add `self._your_field` in `DanmuApp.__init__` (or extend the correct service if it fits ownership rules).
2. Register the name in [runtime-state-map.md](runtime-state-map.md) (backtick field name).
3. If exposed to Web, add it via `StatusSnapshotBuilder` (or a new public façade)—not raw reads in `web_api`.
4. Run `python scripts/boundary_guard.py`.

## Read-only projections

- **`RuntimeState`**: snapshot for tests/tools; must use `GenerationPipelineState.from_app()` for generation-related fields—not scattered `getattr(app, "_latest_*")`.
- **`GenerationPipelineState`**: must not write back to `app`, import Qt, or call pipeline functions (`_trigger_api_call`, `_consume_reply_queue`, …).

## Observability and logging

- Pipeline issues: application log (`DanmuApp.logger`) with structured `reason=` fields — see [main-pipeline-sequence.md](main-pipeline-sequence.md#observability-structured-log-reason) and [AGENTS.md](../AGENTS.md).
- Optional debug env: `DANMU_SCENE_DEBUG`, `DANMU_API_SCHEDULE_DEBUG`, `DANMU_DEDUP_PROFILE`, `DANMU_IMAGE_METRICS` (see [WEB_CONSOLE.md](WEB_CONSOLE.md)).
- Web `PUT /api/config`: HTTP returns `ok` after `save_config_requested.emit()`; actual SQLite write runs on the main thread in `WebConsoleBridge._on_save_config`. Failures log on the main thread and surface via `set_web_error_status` (toast may show success briefly before the slot runs).

## Known limitations

- `GET /api/status` and `GET /api/diagnostics` build snapshots on the HTTP (uvicorn) thread via public façades. Full main-thread marshaling for reads is deferred; do not read `danmu_app._*` from routes.

## Config and storage

- Web config changes: `apply_web_config_payload()` → `ConfigService` / `apply_web_config_patch()`.
- `ConfigStore.set()` updates in-memory cache only after a successful commit (same semantics as `set_batch`).
- Do not spread `config.conn` beyond the whitelist in [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md).

## Maintainer registry

Full field list (machine-checked): [runtime-state-map.md](runtime-state-map.md).

Architecture baseline (short): [final-architecture-baseline.md](final-architecture-baseline.md).

Historical phase notes: [archive/architecture-phases/](archive/architecture-phases/).
