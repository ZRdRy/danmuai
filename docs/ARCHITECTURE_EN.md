# Architecture

## Overall Structure

- `main.py`
  - `DanmuApp` owns the state machine, screenshot scheduling, reply consumption, failure backoff, and shutdown flow.
  - `MainWindow` hosts the Settings, Logs, Template, and Control pages.
- `app/snipper.py`
  - `ScreenCapturer` grabs the configured region from the primary screen.
- `app/ai_client.py`
  - `AiWorker` runs synchronous `httpx` requests from a `QThreadPool` worker thread and returns results through Qt signals.
- `app/reply_queue.py`
  - `AIReplyFIFOBuffer` keeps a bounded reply queue so memory cannot grow without limit.
- `app/reply_parser.py`
  - Parses model output and normalizes it into exactly 5 danmu comments.
- `app/overlay.py` + `app/danmu_engine.py`
  - Handle danmu layout, track scheduling, collision avoidance, and rendering.

## Key Runtime Sequence

1. `DanmuApp.start()` resets runtime state and triggers the next screenshot cycle.
2. `DanmuApp._screenshot_loop()` captures the configured region and produces a new `screenshot_id` and `scene_generation`.
3. `AiRunnable.run()` compresses the screenshot in a worker thread, then calls `AiWorker._request()`.
4. `AiWorker` emits either `finished` or `error`.
5. `DanmuApp._on_ai_reply()` validates freshness, normalizes the output to 5 comments, and pushes it into the bounded queue.
6. `DanmuApp._consume_reply_queue()` dispatches queued replies into `DanmuEngine` at an adaptive pace based on current density.

## Stability Constraints

- Each screenshot has a monotonically increasing `screenshot_id`.
- Scene fingerprint changes increment `scene_generation` and clear stale queued replies and pending danmu.
- Stale replies, replies from old scenes, and replies beyond the freshness threshold are dropped.
- `AiWorker` uses request timeouts and repeated-failure backoff to avoid hanging forever.
- `quit()` calls `stop()`, marks workers as stopping, closes HTTP clients, and waits briefly for the thread pool to settle.

## Release Boundaries

- The current version supports only the primary screen.
- Screenshot region selection is still coordinate-based; there is no visual region picker yet.
- History stores danmu text only and does not persist raw screenshots.
