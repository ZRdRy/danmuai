import time
from types import SimpleNamespace

from app.reply_queue import AIReplyFIFOBuffer, QueuedReply
from main import DanmuApp


class FakeLogger:
    def __init__(self):
        self.debug_messages = []
        self.info_messages = []
        self.error_messages = []

    def debug(self, message):
        self.debug_messages.append(message)

    def info(self, message):
        self.info_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)


class FakeControlPanel:
    def update_stats(self, *a):
        pass
    def update_system_status(self, *a):
        pass
    def set_error_status(self, *a):
        pass


class FakeWindow:
    def __init__(self):
        self.control_panel = FakeControlPanel()


class FakeConfig:
    def get(self, key, default=""):
        return default
    def get_int(self, key, default=0):
        return default
    def get_float(self, key, default=0.0):
        return default


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.running = False
        self.screen_width = 1920.0

    def add_text(self, content, persona, batch_id=0):
        self.calls.append((content, persona))
        return SimpleNamespace(content=content, persona=persona, batch_id=batch_id, x=2000.0, speed=2.2)

    def max_on_screen(self):
        return 0

    def current_display_count(self):
        return 0

    def get_display_count(self):
        return 0

    def right_zone_count(self):
        return 0


class FakeHistory:
    def __init__(self):
        self.calls = []

    def add(self, content, persona, round_num):
        self.calls.append((content, persona, round_num))


class FakeHistoryWriter:
    def __init__(self):
        self.calls = []

    def enqueue(self, content, persona, round_num, image_bytes=None):
        self.calls.append((content, persona, round_num, image_bytes))

    def stop(self):
        pass


class FakeTimer:
    def __init__(self):
        self.active = False
        self.started = 0
        self.stopped = 0
        self._interval = 800

    def isActive(self):
        return self.active

    def start(self, ms=0):
        self.active = True
        self.started += 1

    def stop(self):
        self.active = False
        self.stopped += 1

    def interval(self):
        return self._interval

    def setInterval(self, ms):
        self._interval = ms


def test_reply_fifo_buffer_preserves_completion_order():
    buffer = AIReplyFIFOBuffer()
    buffer.push(QueuedReply("persona-a", 1, 0, "first", 1, 1, 1.0, 1))
    buffer.push(QueuedReply("persona-b", 2, 0, "second", 2, 2, 2.0, 1))
    buffer.push(QueuedReply("persona-c", 3, 0, "third", 3, 3, 3.0, 1))

    assert buffer.pop().content == "first"
    assert buffer.pop().content == "second"
    assert buffer.pop().content == "third"
    assert buffer.is_empty()


def test_reply_fifo_buffer_keeps_eight_latest_items_by_default():
    buffer = AIReplyFIFOBuffer()

    for i in range(9):
        buffer.push(QueuedReply("persona", i, 0, f"msg-{i}", i))

    assert buffer.size() == 8
    assert buffer.pop().content == "msg-1"


def test_ai_reply_queue_uses_request_context_and_fifos_results():
    app = DanmuApp.__new__(DanmuApp)
    app.logger = FakeLogger()
    app.engine = FakeEngine()
    app.history = FakeHistory()
    app.history_writer = FakeHistoryWriter()
    app.reply_buffer = AIReplyFIFOBuffer(max_items=8)
    app.danmu_queue = app.reply_buffer
    app.reply_timer = FakeTimer()
    app.ai_in_flight = 1
    app.MAX_IN_FLIGHT = 1
    app._screenshot_scheduled = False
    app._schedule_next_screenshot = lambda delay_ms: None
    app.reply_timer.active = False
    app._queue_low_watermark = 3
    app._queue_fallback_keep = 3
    app._queue_run_dry_window_ms = 2000
    app._queue_batch_size = 5
    app.danmu_count = 0
    app.screenshot_round = 10
    app._latest_displayed_round = 0
    app._rtt_history = []
    app._request_started_at_by_id = {}
    app.config = FakeConfig()
    app.window = FakeWindow()
    app._consecutive_failures = 0
    app._failure_backoff_paused = False
    app._last_error_message = ""
    app._scene_generation = 0
    app._latest_requested_screenshot_id = 0
    app._latest_queued_screenshot_id = 0
    app._latest_displayed_screenshot_id = 0
    app._is_generating = False
    app._batch_id = 0
    app._current_batch = None
    app._total_input_tokens = 0
    app._total_output_tokens = 0
    app._start_time = 0.0

    now = time.monotonic()
    app._on_ai_reply('["A1", "A2"]', "persona-1", 10, 10, now, 0)
    app._on_ai_reply('["B1"]', "persona-2", 11, 11, now, 0)

    assert app.reply_buffer.size() == 7

    assert app.engine.calls == [
        ("A1", "persona-1"),
        ("B1", "persona-2"),
    ]
    assert app.history_writer.calls == [
        ("A1", "persona-1", 10, None),
        ("B1", "persona-2", 11, None),
    ]
