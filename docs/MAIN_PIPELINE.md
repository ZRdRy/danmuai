# Main pipeline

This document describes the **current** visual path from screenshot to on-screen danmaku. It matches `main.py` as of the normal-only display mode (no realtime/rhythm timers).

For a step table used by Boundary Guard, see [main-pipeline-sequence.md](main-pipeline-sequence.md).

## Scope

`截图 → AI 请求 → 回复解析 → 回复队列 → DanmuEngine → Overlay → HistoryWriter`

Mic insert and Web console are out of scope except where noted.

## Flow

```text
DanmuApp.start()
  → screenshot_timer.start(normal_recognition_interval_ms)
  → _on_normal_capture_tick()                    [immediate first tick]

screenshot_timer.timeout
  → _on_screenshot_timer()
  → _on_normal_capture_tick()
       → if visual in-flight: return (debug skip; warning if elapsed ≥ VISUAL_INFLIGHT_WARN_SEC)
       → _capture_screenshot()
            → ScreenCapturer.grab()
            → if None / isNull / zero size: return (no screenshot_id++; reason=invalid_pixmap)
            → update _latest_screenshot / _latest_screenshot_id / time
            → _collect_activity_observation()
       → if no pixmap: return
       → _trigger_api_call(source="normal_interval")
            → RequestScheduler.block_reason() / record_trigger_time()
            → QThreadPool.start(AiRunnable)
                 → compress_screenshot → AiWorker._request()
            → _on_ai_reply() [main thread, signal]
                 → parse_ai_reply_with_memory / normalize_reply_batch
                 → _enqueue_reply_batch → reply_buffer.extend(...)
                 → schedule _consume_reply_queue via reply_timer

reply_timer.timeout (adaptive interval)
  → _consume_reply_queue()
       → reply_buffer.pop()
       → engine.add_text() → overlay measure/prepare pixmap
       → history_writer.enqueue()
       → overlay render loop (_tick / paintEvent)

HistoryWriter.flush()                              [background batch SQLite]
```

## Key functions

| Step | Entry | Notes |
|------|--------|------|
| Start | `DanmuApp.start()` | Resets session fields, starts screenshot/reply/pool timers, shows overlay |
| Capture tick | `_on_normal_capture_tick()` | Skips if `ai_in_flight` / generating; logs `inflight_watchdog` after 45s (no auto-reset) |
| Capture | `_capture_screenshot()` | Valid frame only; invalid pixmap logged, id not incremented |
| Trigger | `_trigger_api_call()` | Registers meta + `RequestTimingService.mark_started`; starts `AiRunnable` |
| Reply | `_on_ai_reply()` | Tokens, parse, memory update, enqueue |
| Dequeue | `_consume_reply_queue()` | Dedup engine, history, adaptive `reply_timer` |
| Render | `DanmuOverlay.start_render_loop()` | 16 ms timer when items animate |

## Identifiers

- **`screenshot_id`**: incremented only after a **valid** capture in `_capture_screenshot()`; stamped on requests and `QueuedReply`.
- **`scene_generation`**: reset on `start()`/`stop()`; passed through AI/reply for memory; not advanced by a live scene-change loop today.
- **`request_round`**: `screenshot_round` for visual; negative seq for mic.
- **`request_timing_id`**: `{request_round}:{screenshot_id}:{scene_generation}` (`_reply_request_id`); used for `_pending_request_meta` keys and `RequestTimingService` RTT samples.

## Scheduling services

- **`RequestScheduler`**: `min_api_interval`, in-flight gate, `last_api_trigger_at`.
- **`RequestTimingService`**: `mark_started` / `consume_timing` on composite `request_timing_id` (mic and visual on the same `screenshot_id` do not collide); RTT deque and avg for logging/cooldown hints.

`VISUAL_INFLIGHT_WARN_SEC` (45s) is a **module constant** in `main.py`, not a `DanmuApp` runtime field.

Do not bypass these when adding throttle or timing features.

## What not to do

- Do not reintroduce a second visual trigger path (old rhythm / realtime preload) without updating [main-pipeline-sequence.md](main-pipeline-sequence.md) and running Boundary Guard.
- Do not call `DanmuEngine` or `Overlay` from `app/web_api` or `app/application/*` services.
- Do not parse AI output in the Web layer.

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — system overview
- [RUNTIME_STATE.md](RUNTIME_STATE.md) — snapshots and state objects
- [CONTRIBUTING_ARCHITECTURE.md](CONTRIBUTING_ARCHITECTURE.md) — contributor boundaries
