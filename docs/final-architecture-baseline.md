# Final architecture baseline

Short reference for maintainers and Boundary Guard. For onboarding, read [ARCHITECTURE.md](ARCHITECTURE.md) and [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md).

## Roles

| Component | Role |
|-----------|------|
| `DanmuApp` | Bootstrap, Qt lifecycle, pipeline orchestration, compatibility façades |
| `RuntimeState` | Read-only projection only |
| `StatusSnapshotBuilder` | `/api/status` |
| `DiagnosticSnapshotBuilder` | `/api/diagnostics` (read-only) |
| `RequestScheduler` | Schedule gates; owns `last_api_trigger_at` |
| `RequestTimingService` | RTT / `request_started_at_by_id` / `rtt_history` |
| `StatsState` | Counters and session runtime |
| `WebRuntimeState` | Web error + display cache |
| `GenerationPipelineState` | Read-only generation field projection |
| Boundary Guard | Enforces boundaries on changed lines |

## Migrated ownership

- `_last_api_trigger_at` → `RequestScheduler`
- `_request_started_at_by_id`, `_rtt_history` → `RequestTimingService`
- Stats / web display fields → `StatsState` / `WebRuntimeState`

`DanmuApp` may delegate; do not add new direct writes to migrated fields.

## Frozen on `DanmuApp` (do not move without explicit decision)

`ai_in_flight`, `_pending_request_meta`, `_inflight_screenshot_id`, `_scene_generation`, `reply_buffer`, `_latest_screenshot`, `_latest_screenshot_id`, `QTimer`, `QThreadPool`, `QPixmap`, `_mic_service`.

Do not rewrite `_trigger_api_call`, `_on_ai_reply`, `_consume_reply_queue`, or split `DanmuEngine`/`Overlay` in drive-by work.

## Before adding or removing behavior

1. Entry point and state fields  
2. Timers / threads → update [main-pipeline-sequence.md](main-pipeline-sequence.md)  
3. Web/API fields → snapshot builders only  
4. Schema / storage  
5. Tests + `python scripts/boundary_guard.py`

## More detail

- [RUNTIME_STATE.md](RUNTIME_STATE.md)
- [BOUNDARY_GUARD.md](BOUNDARY_GUARD.md)
- Historical phases: [archive/architecture-phases/](archive/architecture-phases/)
