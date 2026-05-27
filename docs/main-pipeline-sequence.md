# Main Pipeline Sequence

> Human-readable overview: [MAIN_PIPELINE.md](MAIN_PIPELINE.md).  
> Boundary Guard requires this file to change when adding `QTimer` / `QThreadPool` / new thread entry points.

## Scope

Visual path only (normal mode): `截图 → AI 请求 → 回复解析 → 回复队列 → DanmuEngine → Overlay → HistoryWriter`

Mic insert reuses `_on_ai_reply()` / `_enqueue_reply_batch()`; not expanded here.

## Sequence diagram

```text
main.py::DanmuApp.start()
  -> screenshot_timer.start(normal_recognition_interval_ms)
  -> _on_normal_capture_tick()                         [initial tick]

main.py::screenshot_timer.timeout
  -> main.py::_on_screenshot_timer()
  -> main.py::_on_normal_capture_tick()
       -> [if visual in-flight: return]
       -> main.py::_capture_screenshot()
            -> app/snipper.py::ScreenCapturer.grab()
            -> update _latest_screenshot / _latest_screenshot_id / time
            -> _collect_activity_observation()
       -> main.py::_trigger_api_call(source="normal_interval")
            -> RequestScheduler.block_reason / record_trigger_time
            -> QThreadPool.globalInstance().start(AiRunnable)
                 -> compress_screenshot -> app/ai_client.py::AiWorker._request()
        -> main.py::_on_ai_reply()
           -> app/reply_parser.py::parse_ai_reply_with_memory()
           -> app/reply_parser.py::normalize_reply_batch()
           -> main.py::_enqueue_reply_batch()
              -> app/reply_queue.py::AIReplyFIFOBuffer.extend()
           -> main.py::_consume_reply_queue()  [via reply_timer or direct]
              -> app/danmu_engine.py::DanmuEngine.add_text()
              -> history_writer.enqueue()

app/overlay.py::DanmuOverlay.start_render_loop()
  -> _tick() -> DanmuEngine.update() -> paintEvent()
```

## Timers and thread entry points

| Object | Interval / trigger | Handler | Role |
|--------|-------------------|---------|------|
| `screenshot_timer` | `normal_recognition_interval_ms` | `_on_screenshot_timer` | Normal-mode capture + API trigger |
| `reply_timer` | adaptive (single-shot) | `_consume_reply_queue` | Dequeue to engine |
| `_pool_topup_timer` | 500 ms | `_maybe_pool_topup` | Formula pool top-up |
| `_mic_poll_timer` | 400 ms | `_poll_mic_utterance` | Mic RMS endpoint (if enabled) |
| `_live_status_timer` | 500 ms | `_publish_live_status` | Web status push |
| `_lifetime_flush_timer` | (config) | lifetime flush | Stats persistence |
| `QThreadPool` | on demand | `AiRunnable.run` | AI HTTP (visual + mic) |
| `QTimer.singleShot` | variable | `_do_scheduled_screenshot` | Supplemental capture scheduling |

Removed from product: `_rhythm_check_timer`, `_check_rhythm_trigger()`, realtime display mode branch.

## Stage table

| Stage | Entry | Downstream | Key state |
|-------|--------|------------|-----------|
| Start | `DanmuApp.start()` | timers, overlay, `_on_normal_capture_tick` | session reset |
| Capture tick | `_on_normal_capture_tick()` | `_capture_screenshot`, `_trigger_api_call` | skips if in-flight |
| Capture | `_capture_screenshot()` | `ScreenCapturer.grab` | `_latest_screenshot_id++` |
| Trigger | `_trigger_api_call()` | `AiRunnable` | meta, `ai_in_flight` |
| Worker | `AiRunnable.run()` | `AiWorker._request` | compressed image URI |
| Reply | `_on_ai_reply()` | parse, enqueue | tokens, memory |
| Enqueue | `_enqueue_reply_batch()` | `reply_buffer.extend` | `QueuedReply` list |
| Consume | `_consume_reply_queue()` | `engine.add_text`, history | adaptive delay |
| Render | `DanmuOverlay._tick` | `engine.update`, paint | tracks |

## Key fields

- `screenshot_id`: set in `_capture_screenshot()`; validated in `_on_ai_reply()` / consume.
- `scene_generation`: reset on start/stop; carried on requests (memory); not advanced by live scene-change loop today.
- `request_round`: `screenshot_round` for visual; negative for mic.

## Web status side path (unchanged pipeline)

- `WebConsoleBridge.refresh_status()` → `DanmuApp.build_status_snapshot()` → `StatusSnapshotBuilder`.
- Does not participate in capture → overlay data path.

## Non-goals

- Full `_on_ai_error()` backoff branches.
- Web route registration details.
