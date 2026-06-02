"""
P0-005 最小主流程测试

覆盖核心链路：
1. 截图压缩失败路径
2. AI 成功返回入队
3. AI 失败后错误提示 / in-flight 释放
4. 连续失败退避
"""

import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from app.application.generation_pipeline_state import GenerationPipelineState
from app.application.stats_state import StatsState
from app.application.web_runtime_state import WebRuntimeState
from app.config_store import ConfigStore
from app.danmu_engine import DanmuEngine, normalize_danmu_display_text
from app.lifetime_stats import STATS_LIFETIME_RUNTIME_SEC, LifetimeStats
from app.memory.activity import RecentActivityState
from app.overlay import DanmuOverlay
from app.reply_queue import AIReplyFIFOBuffer, QueuedReply
from app.runnable import AiRunnable
from app.scene_memory import SceneMemoryStore
from main import DanmuApp, compress_screenshot, show_startup_notice_if_needed
from PyQt6.QtWidgets import QApplication

from tests.conftest import bind_minimal_danmu_app
from tests.fakes import FakeLifetimeStats, FakeLogger


class FakeConfig:
    def __init__(self, values=None):
        self.values = {}
        self.values.update(values or {})

    def get(self, key, default=""):
        return self.values.get(key, default)

    def get_int(self, key, default=0):
        val = self.values.get(key, default)
        return int(val)

    def get_float(self, key, default=0.0):
        val = self.values.get(key, default)
        return float(val)

    def set(self, key, value):
        self.values[key] = value

    def get_api_key(self):
        return self.values.get("api_key", "")

    def get_region(self):
        return self.values.get("region", (0, 0, 200, 200))


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.running = False
        self.dropped_pending = 0
        self.screen_width = 1920.0
        self._accel_remaining = 0
        self._accel_peak = 1.0
        self.tracks = []

    def add_text(self, content, persona, batch_id=0, scene_generation=0, *, skip_dedup=False, **_kwargs):
        self.calls.append((content, persona))
        return SimpleNamespace(
            content=content,
            persona=persona,
            batch_id=batch_id,
            scene_generation=scene_generation,
            x=2000.0,
            speed=2.2,
        )

    def clear_dedup_window(self):
        pass

    def drop_pending_below_generation(self, min_generation):
        return 0

    def drop_items_below_scene_generation(self, min_generation):
        return 0

    def drop_items_with_batch_id(self, batch_id):
        return 0

    def visible_display_count(self):
        return 0

    def min_on_screen(self):
        return 5

    def deficit_below_min(self):
        return 0

    def current_display_count(self):
        return 0

    def get_display_count(self):
        return 0

    def right_zone_count(self):
        return 0

    def danmu_pool_enabled(self):
        return False

    def needs_refill(self):
        return True

    def drop_pending_items(self):
        self.dropped_pending += 1
        return 1

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


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
        self._single_shot = False

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

    def setSingleShot(self, val):
        self._single_shot = val


class FakeCapturer:
    def __init__(self, pixmap=None):
        self._pixmap = pixmap

    def grab(self):
        return self._pixmap


class FakePixmap:
    def __init__(self, scene_byte, *, is_null: bool = False, width: int = 200, height: int = 200):
        self.scene_byte = scene_byte
        self._is_null = is_null
        self._width = width
        self._height = height

    def isNull(self):
        return self._is_null

    def width(self):
        return self._width

    def height(self):
        return self._height


def _make_minimal_app():
    """创建最小 mock 的 DanmuApp 实例"""
    app = DanmuApp.__new__(DanmuApp)
    object.__setattr__(app, "_dedup_profile_log_at_count", 0)
    object.__setattr__(app, "_scene_generation_bumped_at", 0.0)
    object.__setattr__(app, "_active_scene_probe_size", 16)
    app.logger = FakeLogger()
    app.engine = FakeEngine()
    app.history_writer = FakeHistoryWriter()
    app.reply_buffer = AIReplyFIFOBuffer(max_items=8)
    app.danmu_queue = app.reply_buffer
    app.reply_timer = FakeTimer()
    app.ai_in_flight = 0
    app.MAX_IN_FLIGHT = 1
    app.mic_in_flight = 0
    app.MAX_MIC_IN_FLIGHT = 1
    app._mic_request_seq = 0
    app._mic_batch_id = 0
    app._pending_request_meta = {}
    app.reply_timer.active = False
    app._queue_low_watermark = 3
    app._queue_fallback_keep = 3
    app._queue_batch_size = 5
    app._reply_scene_count = 2
    app._reply_filler_count = 3
    app.stats_state = StatsState()
    app.screenshot_round = 0
    app._latest_displayed_round = 0
    app._rtt_history = []
    app._request_started_at_by_id = {}
    app.config = FakeConfig()
    app.web_runtime_state = WebRuntimeState()
    app._consecutive_failures = 0
    app._failure_backoff_paused = False
    app._last_error_message = ""
    app.MAX_CONSECUTIVE_FAILURES = 5
    app._pending = False
    app._scene_generation = 0
    app._inflight_scene_generation = 0
    app._stale_scene_inflight_drop_count = 0
    app._stale_scene_consume_drop_count = 0
    app._latest_screenshot_id = 0
    app._latest_requested_screenshot_id = 0
    app._latest_queued_screenshot_id = 0
    app._latest_displayed_screenshot_id = 0
    app._last_api_trigger_at = 0.0
    app.screenshot_timer = FakeTimer()
    app.capturer = FakeCapturer(None)
    app._is_generating = False
    app._batch_id = 0
    app._current_batch = None
    app._latest_screenshot = None
    app._latest_screenshot_time = 0.0
    app._inflight_screenshot_id = 0
    app._inflight_started_at = 0.0
    app._stale_drop_count = 0
    app._stale_drop_times = []
    app._screenshot_backoff_level = 0
    app._publish_live_status = lambda: None
    app.web_bridge = None
    app.ai_worker = Mock()
    app._scene_memory = SceneMemoryStore()
    app._activity_state = RecentActivityState()
    app._last_activity_collect_at = 0.0
    app.lifetime_stats = FakeLifetimeStats()
    app.session_run_log = Mock()
    app._lifetime_flush_timer = FakeTimer()
    app._live_status_timer = FakeTimer()
    app._sync_reply_batch_config = DanmuApp._sync_reply_batch_config.__get__(app, DanmuApp)
    app._normal_recognition_interval_ms = DanmuApp._normal_recognition_interval_ms.__get__(app, DanmuApp)
    app._normal_reply_count = DanmuApp._normal_reply_count.__get__(app, DanmuApp)
    app._queue_capacity = DanmuApp._queue_capacity.__get__(app, DanmuApp)
    app._enqueue_reply_batch = DanmuApp._enqueue_reply_batch.__get__(app, DanmuApp)
    app._consume_reply_queue = DanmuApp._consume_reply_queue.__get__(app, DanmuApp)
    app._on_screenshot_timer = DanmuApp._on_screenshot_timer.__get__(app, DanmuApp)
    app._on_normal_capture_tick = DanmuApp._on_normal_capture_tick.__get__(app, DanmuApp)
    app._is_reply_stale = DanmuApp._is_reply_stale.__get__(app, DanmuApp)
    app._reply_request_id = DanmuApp._reply_request_id.__get__(app, DanmuApp)
    app._register_request_meta = DanmuApp._register_request_meta.__get__(app, DanmuApp)
    app._pop_request_meta = DanmuApp._pop_request_meta.__get__(app, DanmuApp)
    app._consume_request_timing = DanmuApp._consume_request_timing.__get__(app, DanmuApp)
    app._get_request_timing_service = DanmuApp._get_request_timing_service.__get__(app, DanmuApp)
    app._release_inflight_for_source = DanmuApp._release_inflight_for_source.__get__(app, DanmuApp)
    app._ensure_stats_state = DanmuApp._ensure_stats_state.__get__(app, DanmuApp)
    app._log_reply_drop = DanmuApp._log_reply_drop.__get__(app, DanmuApp)
    app._update_stats = DanmuApp._update_stats.__get__(app, DanmuApp)
    app._estimated_reply_gap_ms = DanmuApp._estimated_reply_gap_ms.__get__(app, DanmuApp)
    app._record_scene_memory_display = lambda *a, **k: None
    app.state_changed = Mock()
    app._sync_reply_batch_config()
    return app


class DedupFakeEngine(FakeEngine):
    def __init__(self, duplicate_text: str):
        super().__init__()
        self.duplicate_text = duplicate_text
        self.running = True

    def add_text(self, content, persona, batch_id=0, scene_generation=0, *, skip_dedup=False, **_kwargs):
        if not skip_dedup and content == self.duplicate_text:
            return None
        return super().add_text(
            content,
            persona,
            batch_id=batch_id,
            scene_generation=scene_generation,
            skip_dedup=skip_dedup,
        )

    def is_duplicate(self, content: str) -> bool:
        return content == self.duplicate_text


def _start_app_timers(app):
    """Exercise timer setup from DanmuApp.start() without full UI stack."""
    app.reply_buffer.set_max_items(app._queue_capacity())
    app.screenshot_timer.stop()
    app.screenshot_timer.setInterval(app._normal_recognition_interval_ms())
    app.screenshot_timer.start()
    app._live_status_timer.start()
    app._lifetime_flush_timer.start()


def test_normal_mode_start_uses_configured_capture_interval():
    app = _make_minimal_app()
    app.config = FakeConfig(
        {
            "danmu_display_mode": "normal",
            "normal_recognition_interval_sec": "7",
            "api_key": "test-key",
        }
    )
    app._sync_reply_batch_config()
    _start_app_timers(app)
    assert app.screenshot_timer._interval == 7000
    assert app.screenshot_timer.active


def test_normal_mode_enqueues_full_batch_without_prepend_replacement():
    app = _make_minimal_app()
    app.config = FakeConfig({"danmu_display_mode": "normal", "normal_reply_count": "3"})
    app._sync_reply_batch_config()
    app.reply_buffer.set_max_items(app._queue_capacity())

    def enqueue_batch(items: list[str], batch_id: int):
        app._batch_id = batch_id
        app._enqueue_reply_batch(
            "p1",
            1,
            batch_id,
            time.monotonic(),
            0,
            items,
        )

    enqueue_batch(["a", "b"], 1)
    enqueue_batch(["c", "d"], 2)
    assert app.reply_buffer.size() == 4
    popped = [app.reply_buffer.pop().content for _ in range(4)]
    assert popped == ["a", "b", "c", "d"]


def test_normal_tick_skips_while_in_flight():
    app = _make_minimal_app()
    app.config = FakeConfig({"danmu_display_mode": "normal"})
    app.engine.running = True
    grab_count = 0

    def grab():
        nonlocal grab_count
        grab_count += 1
        return FakePixmap(0)

    app.capturer = FakeCapturer(FakePixmap(0))
    app.capturer.grab = grab
    app.ai_in_flight = 1
    app._on_normal_capture_tick()
    assert grab_count == 0


def test_normal_mode_is_reply_stale_ignores_scene_generation():
    app = _make_minimal_app()
    app.config = FakeConfig({"danmu_display_mode": "normal", "drop_stale": "0"})
    stale, reason = app._is_reply_stale(1, time.monotonic(), scene_generation=0)
    assert stale is False
    assert reason == ""
    stale2, reason2 = app._is_reply_stale(1, time.monotonic(), scene_generation=99)
    assert stale2 is False
    assert reason2 == ""


def test_normal_mode_no_stale_ttl_when_drop_stale_enabled():
    app = _make_minimal_app()
    app.config = FakeConfig(
        {
            "danmu_display_mode": "normal",
            "drop_stale": "1",
            "normal_recognition_interval_sec": "5",
        }
    )
    captured = time.monotonic() - 60.0
    stale, reason = app._is_reply_stale(1, captured, scene_generation=0, source="ai")
    assert stale is False
    assert reason == ""


def test_on_ai_reply_enqueues_despite_stale_screenshot_id(monkeypatch):
    """旧 screenshot_id / captured_at 仍入队；见 tests/test_scene_freshness.py 同族用例。"""
    import main as main_mod

    app = _make_minimal_app()
    app.ai_in_flight = 1
    app._latest_screenshot_id = 100
    app._register_request_meta(10, 1, 0, "visual")
    drop_calls = []
    app._log_reply_drop = lambda *args, **kwargs: drop_calls.append(args)
    monkeypatch.setattr(main_mod, "parse_ai_reply_with_memory", lambda text, sg: (["lagged"], None))
    monkeypatch.setattr(main_mod, "normalize_reply_batch", lambda raw_items, **kwargs: raw_items)
    app._on_ai_reply = main_mod.DanmuApp._on_ai_reply.__get__(app, main_mod.DanmuApp)
    app._consume_reply_queue = lambda: None
    app._publish_live_status = lambda: None

    old_captured = time.monotonic() - 120.0
    app._on_ai_reply('["lagged"]', "persona-1", 10, 1, old_captured, 0)

    assert drop_calls == []
    assert app._stale_scene_inflight_drop_count == 0
    assert not app.reply_buffer.is_empty()


def test_normal_mode_consumes_all_non_duplicate_items():
    app = _make_minimal_app()
    app.config = FakeConfig(
        {
            "danmu_display_mode": "normal",
            "drop_stale": "0",
        }
    )
    app._sync_reply_batch_config()
    app.engine = DedupFakeEngine("dup")
    app.engine.running = True
    now = time.monotonic()
    for idx, text in enumerate(["ok1", "dup", "ok2"]):
        app.reply_buffer.push(
            QueuedReply(
                "p1",
                1,
                idx,
                text,
                screenshot_id=1,
                captured_at=now,
                scene_generation=0,
            )
        )
    for _ in range(3):
        app._consume_reply_queue()
    assert [c[0] for c in app.engine.calls] == ["ok1", "ok2"]
    assert len(app.history_writer.calls) == 2


def test_history_enqueue_matches_display_truncation():
    """BUG-015: history row content matches on-screen truncation."""
    app = _make_minimal_app()
    app.config = FakeConfig({"danmu_max_chars": "8", "drop_stale": "0"})
    app.engine.running = True
    raw = "一二三四五六七八九十"
    expected = normalize_danmu_display_text(raw, app.config)
    now = time.monotonic()
    app.reply_buffer.push(
        QueuedReply(
            "p1",
            1,
            0,
            raw,
            screenshot_id=1,
            captured_at=now,
            scene_generation=0,
        )
    )
    app._consume_reply_queue()
    assert len(app.history_writer.calls) == 1
    assert app.history_writer.calls[0][0] == expected
    assert app.history_writer.calls[0][0] != raw


def test_inject_test_danmu_batch_reuses_history_truncation_path():
    app = _make_minimal_app()
    app.config = FakeConfig({"danmu_max_chars": "8", "drop_stale": "0"})
    raw = "一二三四五六七八九十"
    expected = normalize_danmu_display_text(raw, app.config)

    result = app.inject_test_danmu_batch([raw], persona_id="验收")

    assert result["ok"] is True
    assert result["queued"] == 1
    assert result["expected_texts"] == [expected]
    assert result["visible_texts"] == []
    assert result["active_texts"] == []
    assert app.reply_buffer.is_empty()
    assert len(app.history_writer.calls) == 1
    assert app.history_writer.calls[0][0] == expected
    assert app.history_writer.calls[0][0] != raw


def test_inject_test_danmu_batch_rejects_empty_items():
    app = _make_minimal_app()

    with pytest.raises(ValueError, match="请至少提供一条弹幕"):
        app.inject_test_danmu_batch(["", "   "])


def test_compress_screenshot_failure_path():
    """测试截图压缩失败时 in-flight 计数正确释放"""
    # 模拟一个会导致压缩失败的 pixmap
    mock_pixmap = Mock()
    mock_pixmap.toImage.side_effect = RuntimeError("has been deleted")

    # 创建 mock worker
    mock_worker = Mock()
    mock_worker._stopping = False

    # 创建 runnable 并执行
    runnable = AiRunnable(
        worker=mock_worker,
        pixmap=mock_pixmap,
        system_pt="system",
        user_pt="user",
        persona_id="test-persona",
        request_round=1,
        screenshot_id=1,
        captured_at=1.0,
        scene_generation=0,
        compress_fn=compress_screenshot
    )

    # 执行 run 方法（会捕获异常并发射错误信号）
    runnable.run()

    # 验证错误信号被发射
    mock_worker._emit_safe.assert_called_once()
    call_args = mock_worker._emit_safe.call_args
    assert call_args[0][0] == "error"
    assert "压缩失败" in call_args[0][1]


def test_runnable_request_uncaught_exception_emits_error():
    """_request 阶段未捕获异常时应 emit error（与压缩失败对称）"""
    mock_pixmap = Mock()
    mock_pixmap.width.return_value = 100
    mock_pixmap.height.return_value = 80

    mock_worker = Mock()
    mock_worker._stopping = False
    mock_worker._request.side_effect = ValueError("bad config")

    runnable = AiRunnable(
        worker=mock_worker,
        pixmap=mock_pixmap,
        system_pt="system",
        user_pt="user",
        persona_id="test-persona",
        request_round=2,
        screenshot_id=3,
        captured_at=2.0,
        scene_generation=1,
        compress_fn=lambda _p: "data:image/jpeg;base64,abc",
        image_quality=85,
    )
    runnable.run()

    mock_worker._emit_safe.assert_called_once()
    call_args = mock_worker._emit_safe.call_args
    assert call_args[0][0] == "error"
    assert "bad config" in call_args[0][1]


def test_runnable_request_failure_releases_in_flight():
    """_request 异常经 error 信号回主线程后应释放 ai_in_flight"""
    from app.ai_client import AiWorker
    from PyQt6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])

    app = _make_minimal_app()
    worker = AiWorker(app.config)
    app.ai_worker = worker
    app._on_ai_error = DanmuApp._on_ai_error.__get__(app, DanmuApp)
    worker.error.connect(lambda *args: app._on_ai_error(*args))

    app.ai_in_flight = 1
    app._is_generating = True
    app._register_request_meta(2, 3, 1, "visual")

    mock_pixmap = Mock()
    mock_pixmap.width.return_value = 100
    mock_pixmap.height.return_value = 80

    def _raise_request(*_args, **_kwargs):
        raise ValueError("bad config")

    worker._request = _raise_request

    runnable = AiRunnable(
        worker=worker,
        pixmap=mock_pixmap,
        system_pt="system",
        user_pt="user",
        persona_id="test-persona",
        request_round=2,
        screenshot_id=3,
        captured_at=2.0,
        scene_generation=1,
        compress_fn=lambda _p: "data:image/jpeg;base64,abc",
        image_quality=85,
    )
    runnable.run()
    QApplication.processEvents()

    assert app.ai_in_flight == 0
    assert app._is_generating is False


def test_ai_success_reply_enqueued():
    """测试 AI 成功返回后弹幕正确入队"""
    app = _make_minimal_app()
    app.ai_in_flight = 1
    app.screenshot_round = 10

    app._on_ai_reply('["???A", "???B"]', "persona-1", 10, 10, time.monotonic(), 0)

    assert app.ai_in_flight == 0
    assert app._is_generating is False
    assert app.reply_buffer.size() == 1
    assert len(app.engine.calls) >= 1
    assert app._consecutive_failures == 0
    assert app._failure_backoff_paused is False


def test_legacy_stat_fields_proxy_to_stats_state():
    app = _make_minimal_app()

    app.danmu_count = 3
    app._total_input_tokens = 11
    app._total_output_tokens = 7
    app._start_time = 5.5

    assert app.stats_state.danmu_count == 3
    assert app.stats_state.total_input_tokens == 11
    assert app.stats_state.total_output_tokens == 7
    assert app.stats_state.start_time == 5.5


def test_legacy_web_error_fields_proxy_to_web_runtime_state():
    app = _make_minimal_app()

    DanmuApp._set_error_status_safe(app, "AI timeout", True)

    assert app.web_runtime_state.error_message == "AI timeout"
    assert app.web_runtime_state.is_error is True


def test_older_reply_not_dropped_in_normal_mode():
    """普通模式不做 newer-frame supersede，旧截图回复仍会入队展示"""
    app = _make_minimal_app()
    app.ai_in_flight = 1
    app._latest_requested_screenshot_id = 11

    app._on_ai_reply('["old reply"]', "persona-1", 10, 10, time.monotonic(), 0)

    assert app.ai_in_flight == 0
    assert len(app.engine.calls) >= 1
    assert not any("superseded_by_newer_request" in msg for msg in app.logger.info_messages)


def test_ai_error_releases_in_flight():
    """测试 AI 失败后错误提示和 in-flight 释放"""
    app = _make_minimal_app()
    app.ai_in_flight = 2
    app.MAX_CONSECUTIVE_FAILURES = 5  # 确保不会触发退避

    # 模拟 AI 错误
    app._on_ai_error("AI timeout", "persona-1", 5, 5, time.monotonic(), 0)

    # 验证 in-flight 减少
    assert app.ai_in_flight == 1

    # 验证错误记录
    assert app._consecutive_failures == 1
    assert app._last_error_message == "AI timeout"

    assert app._web_error_is_error is True
    assert app._web_error_message == "AI timeout"


def test_nonfatal_ai_error_schedules_next_screenshot():
    """测试非致命 AI 错误不会中断节奏定时器调度"""
    app = _make_minimal_app()
    app.engine.running = True
    app.ai_in_flight = 1

    app._on_ai_error("AI timeout", "persona-1", 5, 5, time.monotonic(), 0)

    assert app._failure_backoff_paused is False
    assert app._is_generating is False


def test_consecutive_failures_triggers_backoff():
    """测试连续失败达到阈值后自动暂停"""
    app = _make_minimal_app()
    app.ai_in_flight = 1
    app.MAX_CONSECUTIVE_FAILURES = 3  # 降低阈值以便测试

    # 模拟连续 3 次失败
    for i in range(3):
        app._on_ai_error(f"AI ??????: error {i}", "persona-1", i, i, 1.0 + i, 0)

    # 验证进入退避状态
    assert app._consecutive_failures == 3
    assert app._failure_backoff_paused is True

    assert app._web_error_is_error is True
    assert "连续" in app._web_error_message


def test_fatal_error_immediate_backoff():
    """测试致命错误（如 401）立即暂停截图"""
    app = _make_minimal_app()
    app.ai_in_flight = 1

    # 模拟致命错误（401 认证失败）
    app._on_ai_error("401 API Key failure", "persona-1", 1, 1, time.monotonic(), 0)

    # 验证立即进入退避状态
    assert app._failure_backoff_paused is True
    assert app._consecutive_failures == 1


def test_success_resets_failure_count():
    """测试成功请求后重置失败计数"""
    app = _make_minimal_app()
    app.ai_in_flight = 1
    app._consecutive_failures = 3
    app._failure_backoff_paused = True
    app._last_error_message = "previous error"

    app._on_ai_reply('["??????"]', "persona-1", 10, 10, time.monotonic(), 0)

    assert app._consecutive_failures == 0
    assert app._failure_backoff_paused is False
    assert app._last_error_message == ""


def test_screenshot_loop_respects_backoff():
    """测试截图循环在退避状态下不执行截图"""
    app = _make_minimal_app()
    app.engine.running = True
    app._failure_backoff_paused = True

    app._capture_screenshot()

    assert app.screenshot_round == 0
    assert app._latest_screenshot is None


def test_capture_does_not_advance_scene_generation(monkeypatch):
    """普通模式截图不探测场景跳变，代际保持不变"""
    app = _make_minimal_app()
    app.engine.running = True
    app.reply_buffer.push(QueuedReply("p", 0, 0, "old", scene_generation=0))
    app.capturer = FakeCapturer(FakePixmap(0b1))

    app._capture_screenshot()

    assert app._scene_generation == 0
    assert app.reply_buffer.size() == 1
    assert app._latest_screenshot is not None


def test_capture_while_in_flight_still_updates_frame(monkeypatch):
    app = _make_minimal_app()
    app.engine.running = True
    app._latest_screenshot_id = 3
    app.ai_in_flight = 1
    app.capturer = FakeCapturer(FakePixmap((1 << 16) - 1))

    app._capture_screenshot()

    assert app._scene_generation == 0
    assert app._latest_screenshot_id == 4
    assert app._latest_screenshot is not None


def test_repeated_capture_keeps_scene_generation(monkeypatch):
    app = _make_minimal_app()
    app.engine.running = True
    app.capturer = FakeCapturer(FakePixmap(0b1))

    app._capture_screenshot()

    assert app._scene_generation == 0
    assert app._latest_screenshot is not None


def test_scene_fingerprint_ignores_small_hash_drift(monkeypatch):
    from app.scene_fingerprint import is_scene_change

    prev = 0xAAAAAAAAAAAAAAAA
    cur = prev ^ (1 << 5)
    assert is_scene_change(prev, cur) is False


def test_ai_error_does_not_crash_on_missing_ui():
    """测试 AI 错误处理在 UI 缺失时安全降级"""
    app = _make_minimal_app()
    app.window = None  # 模拟 UI 未初始化

    app._on_ai_error("test error", "persona-1", 1, 1, 1.0, 0)

    assert app._consecutive_failures == 1
    assert app._last_error_message == "test error"


def test_invalid_pixmap_does_not_increment_screenshot_id():
    """无效 pixmap 不应递增 screenshot_id 或缓存帧"""
    app = _make_minimal_app()
    app.engine.running = True
    app._latest_screenshot_id = 5
    app.capturer = FakeCapturer(FakePixmap(0, is_null=True))

    app._capture_screenshot()

    assert app._latest_screenshot_id == 5
    assert app._latest_screenshot is None
    assert any("invalid_pixmap" in msg for msg in app.logger.warning_messages)


def test_empty_ai_reply_logs_warning(monkeypatch):
    """AI 解析结果为空时应记录 warning 便于排障"""
    app = _make_minimal_app()
    app.ai_in_flight = 1
    app._register_request_meta(10, 10, 0, "visual")
    monkeypatch.setattr(
        "main.parse_ai_reply_with_memory",
        lambda _text, _gen: ([], None),
    )
    monkeypatch.setattr(
        "main.normalize_reply_batch",
        lambda raw_items, **_kwargs: raw_items,
    )

    app._on_ai_reply("not-json", "persona-1", 10, 10, time.monotonic(), 0)

    assert any("empty_parse" in msg for msg in app.logger.warning_messages)


def test_capture_failure_reschedules_next_screenshot():
    """测试截图失败不会让主循环卡死（普通模式由 screenshot_timer 驱动）"""
    app = _make_minimal_app()
    app.engine.running = True

    app._capture_screenshot()

    assert app._latest_screenshot is None


def test_legacy_overlay_cache_fields_proxy_to_web_runtime_state():
    app = _make_minimal_app()

    app._cached_danmu_lines = 14
    app._cached_layout_mode = "windowed"

    assert app.web_runtime_state.cached_danmu_lines == 14
    assert app.web_runtime_state.cached_layout_mode == "windowed"


def test_generation_pipeline_state_is_read_only_projection():
    app = _make_minimal_app()
    app._active_scene_probe_size = 32
    app._scene_generation_bumped_at = 4.5
    app._last_activity_collect_at = 2.5
    app._latest_displayed_round = 6
    app._latest_requested_screenshot_id = 12
    app._latest_queued_screenshot_id = 11
    app._latest_displayed_screenshot_id = 10

    state = GenerationPipelineState.from_app(app)

    assert state.active_scene_probe_size == 32
    assert state.scene_generation_bumped_at == 4.5
    assert state.last_activity_collect_at == 2.5
    assert state.latest_displayed_round == 6
    assert state.latest_requested_screenshot_id == 12
    assert state.latest_queued_screenshot_id == 11
    assert state.latest_displayed_screenshot_id == 10
    assert app._active_scene_probe_size == 32
    assert app._scene_generation_bumped_at == 4.5


def test_show_startup_notice_on_first_run(monkeypatch):
    from unittest.mock import MagicMock

    from PyQt6.QtWidgets import QMessageBox

    notice = "未找到配置文件，已创建默认配置，请先检查 API Key 等基础设置。"
    config = MagicMock()
    config.get_startup_notice.return_value = notice
    logger = FakeLogger()
    dialog_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: dialog_calls.append(args),
    )

    assert show_startup_notice_if_needed(config, logger) is True
    assert len(dialog_calls) == 1
    assert dialog_calls[0][2] == notice
    assert any(notice in msg for msg in logger.info_messages)


def test_init_normalizes_legacy_realtime_display_mode_config():
    app = DanmuApp.__new__(DanmuApp)
    app.config = FakeConfig({"danmu_display_mode": "realtime"})
    app._normalize_legacy_display_mode_config = DanmuApp._normalize_legacy_display_mode_config.__get__(
        app,
        DanmuApp,
    )

    app._normalize_legacy_display_mode_config()

    assert app.config.get("danmu_display_mode") == "normal"


def test_schedule_webview_skipped_when_startup_terminal_failed(monkeypatch):
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "webview")
    object.__setattr__(app, "webview_shell", None)
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server._bind_failed.set()
    object.__setattr__(app, "web_server", server)

    scheduled = []
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: scheduled.append(ms),
    )

    app._schedule_webview_attach("/")
    assert scheduled == []


def test_schedule_webview_runs_when_startup_slow(monkeypatch):
    import threading
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "webview")
    object.__setattr__(app, "webview_shell", None)
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)

    def _sleep() -> None:
        time.sleep(5.0)

    server._thread = threading.Thread(target=_sleep, daemon=True)
    server._thread.start()

    scheduled = []
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: scheduled.append(ms),
    )
    try:
        object.__setattr__(app, "web_server", server)
        app._schedule_webview_attach("/")
        assert scheduled == [800]
    finally:
        server._bind_failed.set()
        server._thread.join(timeout=1.0)


def test_schedule_webview_attach_retries_after_handshake_failure(monkeypatch):
    from unittest.mock import MagicMock

    from main import _WEBVIEW_ATTACH_RETRY_MS

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "webview")
    object.__setattr__(app, "webview_shell", None)
    server = MagicMock()
    server.startup_ok = True
    server.base_url = "http://127.0.0.1:18765"
    server._browser_launch_opened = False
    object.__setattr__(app, "web_server", server)

    attach_count = [0]
    destroy_count = [0]

    class FakeShell:
        def destroy(self):
            destroy_count[0] += 1

        def is_running(self):
            return False

        def is_handshake_pending(self):
            return False

    def fake_attach(danmu, srv, *, initial_path="/", on_handshake_failed=None):
        attach_count[0] += 1
        shell = FakeShell()
        danmu.webview_shell = shell
        if attach_count[0] == 1 and on_handshake_failed is not None:
            on_handshake_failed()
        return shell

    def fake_single_shot(ms, cb):
        if ms == _WEBVIEW_ATTACH_RETRY_MS:
            cb()

    monkeypatch.setattr("app.webview_shell.attach_webview_shell", fake_attach)
    monkeypatch.setattr("main.QTimer.singleShot", fake_single_shot)
    monkeypatch.setattr("app.webview_shell.wait_for_http_server", lambda *a, **k: True)
    monkeypatch.setattr(
        "app.web_console.clear_startup_attach_error_if_needed",
        lambda _s: None,
    )

    app._schedule_webview_attach("/", attempt=1)

    assert attach_count[0] == 2
    assert destroy_count[0] == 1


def test_open_web_console_when_ready_skips_attach_on_terminal_failure(monkeypatch):
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    object.__setattr__(app, "webview_shell", None)
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server._bind_failed.set()
    object.__setattr__(app, "web_server", server)

    attach_calls = []
    notified = []
    monkeypatch.setattr(
        "app.webview_shell.attach_webview_shell",
        lambda *args, **kwargs: attach_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "app.webview_shell.notify_web_console_failure",
        lambda danmu, key, **kw: notified.append(key),
    )
    monkeypatch.setattr(
        "app.webview_shell.wait_for_http_server",
        lambda url, timeout: False,
    )

    app._open_web_console_when_ready("/")
    assert attach_calls == []
    assert notified == ["web_console.startup_failed"]
    assert server._startup_failure_user_notified is True

    app._open_web_console_when_ready("/")
    assert notified == ["web_console.startup_failed"]


def test_webview_recovers_after_delayed_server_ready(monkeypatch):
    """BUG-004 sub-scenario: slow startup; HTTP becomes ready within retry window."""
    import threading

    from app.web_console import (
        WebConsoleBridge,
        WebConsoleServer,
        classify_web_console_startup,
    )

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "webview")
    object.__setattr__(app, "webview_shell", None)
    object.__setattr__(
        app,
        "set_web_error_status",
        DanmuApp.set_web_error_status.__get__(app, DanmuApp),
    )
    object.__setattr__(
        app,
        "_set_error_status_safe",
        DanmuApp._set_error_status_safe.__get__(app, DanmuApp),
    )
    object.__setattr__(
        app,
        "_ensure_web_runtime_state",
        DanmuApp._ensure_web_runtime_state.__get__(app, DanmuApp),
    )

    bridge = WebConsoleBridge.__new__(WebConsoleBridge)
    bridge.danmu_app = app
    server = WebConsoleServer(bridge)
    server._thread = threading.Thread(target=time.sleep, args=(30.0,), daemon=True)
    server._thread.start()
    server._startup_error_from_attach = True
    app.set_web_error_status("Web 控制台未就绪", is_error=True)

    assert classify_web_console_startup(server) == "slow"

    http_checks: list[int] = []

    def _wait_for_http(url: str, timeout: float) -> bool:
        http_checks.append(1)
        return len(http_checks) >= 2

    attach_calls: list[tuple] = []
    notified: list[str] = []
    scheduled: list[tuple] = []

    monkeypatch.setattr("app.webview_shell.wait_for_http_server", _wait_for_http)
    monkeypatch.setattr(
        "app.webview_shell.attach_webview_shell",
        lambda *args, **kwargs: attach_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "app.webview_shell.notify_web_console_failure",
        lambda danmu, key, **kw: notified.append(key),
    )
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: scheduled.append((ms, cb)),
    )

    try:
        object.__setattr__(app, "web_server", server)
        app._open_web_console_when_ready("/", use_browser=False, attempt=0)

        safety = 0
        while scheduled and not attach_calls and safety < 50:
            safety += 1
            pending = scheduled[:]
            scheduled.clear()
            for _ms, cb in pending:
                cb()

        assert attach_calls, "expected attach_webview_shell after delayed HTTP ready"
        assert len(attach_calls) == 1
        assert app.web_runtime_state.is_error is False
        assert app.web_runtime_state.error_message == ""
        assert server._startup_error_from_attach is False
        assert notified == []
    finally:
        server._bind_failed.set()
        server._thread.join(timeout=1.0)


def test_webview_does_not_recover_when_bind_failed(monkeypatch):
    """Port conflict / bind failure: no in-process webview recovery (restart required)."""
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer, classify_web_console_startup

    app = _make_minimal_app()
    object.__setattr__(app, "webview_shell", None)
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server._bind_failed.set()
    object.__setattr__(app, "web_server", server)

    assert classify_web_console_startup(server) == "failed"

    attach_calls: list[tuple] = []
    notified: list[str] = []
    monkeypatch.setattr(
        "app.webview_shell.attach_webview_shell",
        lambda *args, **kwargs: attach_calls.append(1),
    )
    monkeypatch.setattr(
        "app.webview_shell.wait_for_http_server",
        lambda url, timeout: True,
    )
    monkeypatch.setattr(
        "app.webview_shell.notify_web_console_failure",
        lambda danmu, key, **kw: notified.append(key),
    )

    app._open_web_console_when_ready("/")
    assert attach_calls == []
    assert notified == ["web_console.startup_failed"]


def test_browser_mode_opens_browser_when_server_slow(monkeypatch):
    import threading
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)

    def _sleep() -> None:
        time.sleep(5.0)

    server._thread = threading.Thread(target=_sleep, daemon=True)
    server._thread.start()

    browser_calls = []
    scheduled = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )
    monkeypatch.setattr(
        "app.webview_shell.wait_for_http_server",
        lambda url, timeout: False,
    )
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: scheduled.append(ms),
    )
    try:
        object.__setattr__(app, "web_server", server)
        app._open_web_console_when_ready("/", use_browser=True, attempt=0)
        assert browser_calls == ["/"]
        assert server._browser_launch_opened is True
        assert scheduled == [500]

        app._open_web_console_when_ready("/", use_browser=True, attempt=1)
        assert browser_calls == ["/"]
    finally:
        server._bind_failed.set()
        server._thread.join(timeout=1.0)


def test_browser_mode_opens_browser_when_server_ready(monkeypatch):
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server.startup_ok = True
    object.__setattr__(app, "web_server", server)

    browser_calls = []
    scheduled = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: scheduled.append(ms),
    )

    app._open_web_console_when_ready("/", use_browser=True, attempt=0)
    assert browser_calls == ["/"]
    assert scheduled == []


def test_open_web_console_after_handshake_failed_does_not_reopen_browser(monkeypatch):
    from unittest.mock import MagicMock

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "webview")
    server = MagicMock()
    server.base_url = "http://127.0.0.1:18765"
    object.__setattr__(app, "web_server", server)

    shell = MagicMock()
    shell.is_running.return_value = False
    shell.is_handshake_pending.return_value = False
    shell.handshake_failed = True
    object.__setattr__(app, "webview_shell", shell)

    browser_calls = []
    attach_calls = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )
    monkeypatch.setattr(
        "app.webview_shell.attach_webview_shell",
        lambda *args, **kwargs: attach_calls.append(1),
    )

    app._open_web_console("/#settings")
    assert browser_calls == []
    assert attach_calls == []


def test_browser_mode_skips_browser_on_terminal_failure(monkeypatch):
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server._bind_failed.set()
    object.__setattr__(app, "web_server", server)

    browser_calls = []
    notified = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )
    monkeypatch.setattr(
        "app.webview_shell.notify_web_console_failure",
        lambda danmu, key, **kw: notified.append(key),
    )

    app._open_web_console_when_ready("/", use_browser=True, attempt=0)
    assert browser_calls == []
    assert notified == ["web_console.startup_failed"]


def test_browser_mode_open_web_console_dedupes_browser(monkeypatch):
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "browser")
    object.__setattr__(app, "webview_shell", None)
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server.startup_ok = True
    server._browser_launch_opened = True
    object.__setattr__(app, "web_server", server)

    browser_calls = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )

    app._open_web_console("/#settings")
    assert browser_calls == []


def test_browser_mode_start_without_api_key_dedupes_with_timer_path(monkeypatch):
    import threading
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    object.__setattr__(app, "web_launch_mode", "browser")
    object.__setattr__(app, "webview_shell", None)
    object.__setattr__(app, "config", FakeConfig({}))
    object.__setattr__(app, "tray", MagicMock())
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server._thread = threading.Thread(target=time.sleep, args=(5.0,), daemon=True)
    server._thread.start()
    object.__setattr__(app, "web_server", server)
    object.__setattr__(
        app,
        "_set_error_status_safe",
        DanmuApp._set_error_status_safe.__get__(app, DanmuApp),
    )

    browser_calls = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )
    monkeypatch.setattr(
        "app.webview_shell.wait_for_http_server",
        lambda url, timeout: False,
    )
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: None,
    )

    try:
        DanmuApp.start(app)
        app._open_web_console_when_ready("/#settings", use_browser=True, attempt=0)
        assert browser_calls == ["/#settings"]
        assert server._browser_launch_opened is True
    finally:
        server._bind_failed.set()
        server._thread.join(timeout=1.0)


def test_browser_mode_opens_browser_after_5s_when_server_slow(monkeypatch):
    import threading
    from unittest.mock import MagicMock

    from app.web_console import WebConsoleBridge, WebConsoleServer

    app = _make_minimal_app()
    bridge = WebConsoleBridge(MagicMock())
    server = WebConsoleServer(bridge)
    server._thread = threading.Thread(target=time.sleep, args=(5.0,), daemon=True)
    server._thread.start()
    object.__setattr__(app, "web_server", server)

    browser_calls = []
    scheduled = []
    monkeypatch.setattr(
        "app.web_console.open_web_console_browser",
        lambda srv, p: browser_calls.append(p),
    )
    monkeypatch.setattr(
        "app.webview_shell.wait_for_http_server",
        lambda url, timeout: False,
    )
    monkeypatch.setattr(
        "main.QTimer.singleShot",
        lambda ms, cb: scheduled.append(ms),
    )

    try:
        app._open_web_console_when_ready("/", use_browser=True, attempt=0)
        assert browser_calls == ["/"]
        assert server._browser_launch_opened is True

        scheduled.clear()
        app._open_web_console_when_ready("/", use_browser=True, attempt=10)
        assert browser_calls == ["/"]
        assert scheduled == [500]
    finally:
        server._bind_failed.set()
        server._thread.join(timeout=1.0)


@pytest.fixture()
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.processEvents()


def test_config_change_updates_overlay_font(workspace_tmp, qapp):
    """BUG-007: font_size change via _on_config_changed must refresh overlay font immediately."""
    del qapp
    store = ConfigStore(db_path=workspace_tmp / "font_overlay.db")
    store.set("font_size", "24")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "4")

    engine = DanmuEngine(store)
    engine.set_screen_width(1920.0)
    engine.set_screen_height(1080.0)
    engine.reload_tracks()
    overlay = DanmuOverlay(store, engine)
    engine.overlay = overlay

    app = DanmuApp.__new__(DanmuApp)
    app.config = store
    app.engine = engine
    app.overlay = overlay
    app.web_runtime_state = WebRuntimeState(
        cached_danmu_lines=4,
        cached_layout_mode=store.get("layout_mode", "fullscreen"),
    )
    app.screenshot_timer = FakeTimer()
    app.reply_buffer = AIReplyFIFOBuffer(max_items=8)
    app.hotkey = Mock()
    app._sync_scene_probe_size = lambda: None
    app._sync_mic_service = lambda: None
    app._sync_reply_batch_config = DanmuApp._sync_reply_batch_config.__get__(app, DanmuApp)
    app._normal_recognition_interval_ms = DanmuApp._normal_recognition_interval_ms.__get__(
        app, DanmuApp
    )
    app._queue_capacity = DanmuApp._queue_capacity.__get__(app, DanmuApp)
    app._ensure_web_runtime_state = DanmuApp._ensure_web_runtime_state.__get__(app, DanmuApp)
    app._on_config_changed = DanmuApp._on_config_changed.__get__(app, DanmuApp)

    assert overlay.font.pointSize() == 24

    store.set("font_size", "36")
    app._on_config_changed()

    assert overlay.font.pointSize() == 36


def test_start_seeds_visibility_counts(workspace_tmp, monkeypatch):
    """BUG-003: after start + on-screen danmu, visible display_count must not stay 0."""
    monkeypatch.setattr("app.danmu_engine.random.uniform", lambda _a, _b: 50.0)
    monkeypatch.setattr("app.danmu_engine.random.choices", lambda population, **_kw: population[:1])

    store = ConfigStore(db_path=workspace_tmp / "bug003.db")
    store.set("danmu_speed", "2.0")
    store.set("danmu_lines", "5")

    engine = DanmuEngine(store)
    engine.set_screen_width(1920.0)
    engine.set_screen_height(1080.0)
    engine.reload_tracks()
    engine.start()

    item = engine.add_text("hello", persona="p1")
    assert item is not None
    item.x = 100.0
    engine._refresh_item_visibility(item)

    assert engine.visible_display_count() > 0

    app = SimpleNamespace(
        engine=engine,
        reply_buffer=SimpleNamespace(size=lambda: 0),
        visible_display_count=lambda: engine.visible_display_count(),
        stats_state=StatsState(danmu_count=0, start_time=time.monotonic()),
        web_runtime_state=WebRuntimeState(),
        personae=SimpleNamespace(get_active=lambda: []),
        config=store,
        lifetime_stats=SimpleNamespace(snapshot=lambda **_kwargs: {}),
        session_run_log=SimpleNamespace(list_dicts_newest_first=lambda: []),
        build_live_status_snapshot=lambda: None,
        _region_selection_state="idle",
    )
    status = DanmuApp.build_status_snapshot(app)
    assert status["display_count"] > 0


def test_startup_notice_skipped_when_not_first_run(monkeypatch):
    from unittest.mock import MagicMock

    from PyQt6.QtWidgets import QMessageBox

    config = MagicMock()
    config.get_startup_notice.return_value = ""
    logger = FakeLogger()
    dialog_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: dialog_calls.append(args),
    )

    assert show_startup_notice_if_needed(config, logger) is False
    assert dialog_calls == []
    assert logger.info_messages == []


def test_init_language_uses_seeded_config_not_system_locale(tmp_path, monkeypatch):
    from app.config_defaults import DEFAULT_LANGUAGE, config_value_with_default
    from app.translations import Translator

    monkeypatch.setattr(Translator, "detect_system_language", lambda: "en")

    store = ConfigStore(db_path=tmp_path / "config.db")
    assert store.get("language") == DEFAULT_LANGUAGE

    resolved = Translator.resolve_language(
        config_value_with_default(store, "language")
    )
    assert resolved == DEFAULT_LANGUAGE

    store.close()


def _make_app_for_start_without_api_key(monkeypatch):
    """Minimal DanmuApp stub for BUG-009 start() API-key guard tests."""
    from unittest.mock import MagicMock

    app = DanmuApp.__new__(DanmuApp)
    engine = FakeEngine()
    engine_start_called: list[bool] = []

    def fake_engine_start():
        engine_start_called.append(True)
        engine.running = True

    monkeypatch.setattr(engine, "start", fake_engine_start)

    screenshot_timer = FakeTimer()
    tray = MagicMock()

    object.__setattr__(app, "config", FakeConfig({}))
    object.__setattr__(app, "engine", engine)
    object.__setattr__(app, "logger", FakeLogger())
    object.__setattr__(app, "web_runtime_state", WebRuntimeState())
    object.__setattr__(app, "tray", tray)
    object.__setattr__(app, "web_server", None)
    object.__setattr__(app, "screenshot_timer", screenshot_timer)
    object.__setattr__(app, "web_bridge", None)
    object.__setattr__(
        app,
        "_ensure_web_runtime_state",
        DanmuApp._ensure_web_runtime_state.__get__(app, DanmuApp),
    )
    object.__setattr__(
        app,
        "_set_error_status_safe",
        DanmuApp._set_error_status_safe.__get__(app, DanmuApp),
    )

    return app, engine_start_called, screenshot_timer, tray


def test_start_without_api_key_does_not_start(monkeypatch):
    """BUG-009: start() must not start engine or timers when API key is missing."""
    app, engine_start_called, screenshot_timer, _tray = _make_app_for_start_without_api_key(
        monkeypatch
    )
    DanmuApp.start(app)
    assert engine_start_called == []
    assert app.engine.running is False
    assert screenshot_timer.started == 0


def test_start_without_api_key_surfaces_ui_feedback(monkeypatch):
    """BUG-009: missing API key must set web error state and show tray hint."""
    from app.translations import tr

    app, _engine_start_called, _screenshot_timer, tray = _make_app_for_start_without_api_key(
        monkeypatch
    )
    DanmuApp.start(app)
    msg = tr("app.api_key_missing_warning")
    assert app.web_runtime_state.error_message == msg
    assert app.web_runtime_state.is_error is True
    tray.show_api_key_missing_hint.assert_called_once()


def test_toggle_without_api_key_delegates_to_start_guard(monkeypatch):
    """BUG-009: hotkey/tray toggle path must surface the same guard as start()."""
    app, engine_start_called, _screenshot_timer, tray = _make_app_for_start_without_api_key(
        monkeypatch
    )
    object.__setattr__(app, "toggle", DanmuApp.toggle.__get__(app, DanmuApp))
    DanmuApp.toggle(app)
    assert engine_start_called == []
    assert app.engine.running is False
    assert app.web_runtime_state.is_error is True
    tray.show_api_key_missing_hint.assert_called_once()


def test_stop_flushes_session_runtime_to_lifetime_stats(workspace_tmp):
    """BUG-010: stop path persists session runtime and clears session clock on success."""
    store = ConfigStore(db_path=workspace_tmp / "stop_runtime.db")
    lifetime = LifetimeStats(store)
    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=store, lifetime_stats=lifetime)
    object.__setattr__(
        app,
        "_flush_session_runtime_to_lifetime",
        DanmuApp._flush_session_runtime_to_lifetime.__get__(app, DanmuApp),
    )
    object.__setattr__(app, "_ensure_stats_state", DanmuApp._ensure_stats_state.__get__(app, DanmuApp))

    stats = app.stats_state
    stats.start_time = time.monotonic() - 42.0

    DanmuApp._flush_session_runtime_to_lifetime(app)

    assert stats.start_time == 0.0
    persisted = float(store.get(STATS_LIFETIME_RUNTIME_SEC))
    assert persisted >= 40.0
    assert lifetime.snapshot()["lifetime_runtime_sec"] == persisted


def test_flush_session_runtime_keeps_start_time_when_set_batch_fails(workspace_tmp):
    """BUG-010: failed lifetime flush must not clear session clock."""
    store = ConfigStore(db_path=workspace_tmp / "flush_fail.db")
    lifetime = LifetimeStats(store)
    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app, config=store, lifetime_stats=lifetime)
    object.__setattr__(
        app,
        "_flush_session_runtime_to_lifetime",
        DanmuApp._flush_session_runtime_to_lifetime.__get__(app, DanmuApp),
    )
    object.__setattr__(app, "_ensure_stats_state", DanmuApp._ensure_stats_state.__get__(app, DanmuApp))

    stats = app.stats_state
    stats.start_time = time.monotonic() - 10.0
    before = stats.start_time

    with patch.object(store, "set_batch", side_effect=sqlite3.OperationalError("locked")):
        with pytest.raises(sqlite3.OperationalError):
            DanmuApp._flush_session_runtime_to_lifetime(app)

    assert stats.start_time == before
    assert store.get(STATS_LIFETIME_RUNTIME_SEC, "") in ("", "0", "0.0")


def test_pick_random_skips_deleted_custom_persona(tmp_path):
    from app.personae import PersonaManager, get_reply_contract

    store = ConfigStore(db_path=tmp_path / "persona_pick.db")
    personae = PersonaManager(store)
    contract = get_reply_contract(store)
    personae.save_custom("测试A", contract, "看图发弹幕：")
    personae.set_active(["测试A"])
    personae.delete_custom("测试A")

    assert "测试A" not in personae.get_active()
    assert "测试A" not in personae.list()

    for _ in range(20):
        picked = personae.pick_random()
        assert picked != "测试A"
        system_pt, user_pt = personae.get_prompt(picked)
        assert system_pt
        assert user_pt


def test_delete_custom_prunes_active_personae(tmp_path):
    from app.personae import PersonaManager, get_reply_contract

    store = ConfigStore(db_path=tmp_path / "persona_prune.db")
    personae = PersonaManager(store)
    contract = get_reply_contract(store)
    personae.save_custom("测试A", contract, "看图发弹幕：")
    personae.set_active(["测试A", "吐槽型"])
    personae.delete_custom("测试A")

    stored = store.get_json("active_personae", [])
    assert "测试A" not in stored
    assert "吐槽型" in stored
    assert "测试A" not in personae.get_active()


def test_quit_stops_pool_topup_timer(monkeypatch):
    """BUG-019: quit() must stop _pool_topup_timer even if stop() does not."""
    import PyQt6.QtCore as qtcore

    fake_pool = MagicMock()
    fake_pool.waitForDone.return_value = True

    class _FakeQThreadPool:
        @staticmethod
        def globalInstance():
            return fake_pool

    monkeypatch.setattr(qtcore, "QThreadPool", _FakeQThreadPool)
    monkeypatch.setattr("main.QApplication.quit", MagicMock())

    pool_timer = FakeTimer()
    pool_timer.active = True
    pool_timer.started = 1

    app = SimpleNamespace(
        logger=MagicMock(),
        stop=MagicMock(),
        hotkey=MagicMock(),
        tray=MagicMock(),
        ai_worker=MagicMock(),
        history_writer=MagicMock(),
        config=MagicMock(),
        overlay=MagicMock(),
        webview_shell=None,
        web_server=MagicMock(),
        stop_web_status_timer=MagicMock(),
        _pool_topup_timer=pool_timer,
    )

    DanmuApp.quit(app)

    app.stop.assert_called_once_with()
    assert not pool_timer.isActive()
    assert pool_timer.stopped >= 1
