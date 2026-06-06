"""DanmuAI 应用入口与单例状态机（DanmuApp）。

职责边界（bootstrap / lifecycle / façade）：
- 截图定时、视觉/麦克风双轨 AI 调度、回复队列消费、场景代际淘汰、失败退避
- 与 DanmuOverlay / DanmuEngine 协同上屏；Web 控制台经 bridge 信号回主线程改配置
- 运行态对外展示委托 StatusSnapshotBuilder / DiagnosticSnapshotBuilder，勿在 Web 层拼私有字段

主链路（普通模式，详见 docs/MAIN_PIPELINE.md）：
  screenshot_timer → _on_normal_capture_tick → _capture_screenshot → _trigger_api_call
  → AiRunnable(QThreadPool) → _on_ai_reply → _enqueue_reply_batch → _consume_reply_queue
  → DanmuEngine.add_text → Overlay 绘制

关键设计：
- screenshot_id：每帧截图递增，用于「更新帧优于在途回复」的 supersede 判定
- scene_generation：请求/记忆兼容字段（运行期恒为 0，不做截图 hash 场景判定）
- MAX_IN_FLIGHT=1：并发视觉请求会破坏过期判断与回复顺序，故硬限制为 1

线程：DanmuApp 在 Qt 主线程；AiRunnable 在 QThreadPool 中调 AiWorker，finished 信号队列回主线程。

Phase 4 冻结（勿迁移出本模块）：ai_in_flight、reply_buffer、QTimer/QThreadPool、_latest_screenshot 等，
见 docs/archive/architecture-phases/phase4-freeze.md。

入口：python main.py → main()。
"""
import multiprocessing
import sys
import time
from datetime import datetime

from app.ai_client import AiWorker
from app.api_schedule import min_api_interval_elapsed, pixels_per_second, time_to_anchor_boundary
from app.application.config_service import ConfigService
from app.application.request_scheduler import RequestScheduler
from app.application.request_timing_service import RequestTimingService
from app.application.stats_state import StatsState
from app.application.status_snapshot import StatusSnapshotBuilder
from app.application.web_runtime_state import WebRuntimeState
from app.config_defaults import config_value_with_default
from app.config_store import ConfigStore
from app.danmu_engine import (
    DanmuEngine,
    dedup_profile_enabled,
    log_dedup_profile_summary,
    normalize_danmu_display_text,
)
from app.danmu_read_service import DanmuReadService
from app.history_writer import HistoryWriter
from app.hotkey import HotkeyManager
from app.lifetime_stats import LifetimeStats
from app.live_freshness import (
    LiveStatusSnapshot,
    build_local_fallback_batch,
    is_model_slow,
)
from app.logger import SanitizedLogger
from app.main_helpers import (
    MAX_IN_FLIGHT,
    MAX_MIC_IN_FLIGHT,
    VISUAL_INFLIGHT_WARN_SEC,
    BatchTracker,
    density_right_target,
    memory_enabled,
    memory_mode_from_value,
    memory_tone_hint,
    queue_capacity,
    reply_request_id,
)
from app.main_launch import (
    DEPRECATED_LAUNCH_MSG,
    check_deprecated_launch_args,
    global_exception_hook,
    show_startup_notice_if_needed,
    web_launch_mode_from_argv,
)
from app.main_launch_mixin import DanmuAppLaunchMixin
from app.main_state_mixin import DanmuAppStateMixin
from app.main_web_facade_mixin import DanmuAppWebFacadeMixin
from app.memory.activity import RecentActivityState
from app.memory.activity_prompt import append_activity_line_to_user_pt, format_activity_prompt_line
from app.memory.types import MEMORY_MODE_OFF, bullet_angle_from_index
from app.mic_encode import pcm_to_wav_data_uri
from app.mic_orchestrator import MicOrchestrator
from app.mic_prompt import build_mic_insert_user_pt
from app.mic_service import MicService, mic_mode_enabled
from app.model_providers import (
    mic_audio_supported_for_mic_config,
    resolve_active_model_id,
    resolve_mic_model_id,
)
from app.overlay import DanmuOverlay
from app.personae import (
    PersonaManager,
    append_live_topic_to_system_pt,
    append_nickname_to_system_pt,
    persona_display_name,
)
from app.reply_parser import (
    normalize_reply_batch,
    parse_ai_reply_with_memory,
)
from app.reply_queue import AIReplyFIFOBuffer, QueuedReply
from app.scene_memory import SceneMemoryStore, append_memory_to_user_pt, memory_window_from_config
from app.screenshot_compress import (
    IMAGE_JPEG_QUALITY,
    IMAGE_MAX_WIDTH,
    compress_screenshot,
)
from app.snipper import ScreenCapturer, resolve_screen_index
from app.templates import TemplateManager
from app.translations import Translator, tr
from app.tray import TrayManager
from app.window_info import classify_foreground_window, get_foreground_window_info
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

# Re-export for scripts/tests that import from main.
_DEPRECATED_LAUNCH_MSG = DEPRECATED_LAUNCH_MSG

_MIC_PROBE_WAIT_TIMEOUT_SEC = 120.0
# Mic utterance poll: desync from 500ms main-thread timers; see BUG-018 / W-REFACTOR-BUG-P0P1-014.
MIC_POLL_MS = 600
MIC_POLL_PHASE_MS = 250
_WEBVIEW_ATTACH_MAX_ATTEMPTS = 2
_WEBVIEW_ATTACH_RETRY_MS = 1200

class DanmuApp(DanmuAppLaunchMixin, DanmuAppWebFacadeMixin, DanmuAppStateMixin, QObject):
    """单例应用状态机：bootstrap、生命周期与 Web 公开 façade 的持有者。

    普通模式（当前产品路径）：按 normal_recognition_interval_sec 截图，成功后立即 _trigger_api_call；
    不做截图 hash 场景判定；慢模型下允许轻微滞后，优先弹幕连续。
    麦克风轨：与视觉 ai_in_flight 独立，request_round 为负数以区分 _pending_request_meta。

    配置中遗留的 danmu_display_mode=realtime 会在加载时规范为 normal。

    下列对象/字段禁止在未更新架构文档前迁出本类：reply_buffer、QPixmap 截图缓存、
    QTimer、QThreadPool、_mic_service（见 docs/final-architecture-baseline.md）。
    """

    state_changed = pyqtSignal(bool)  # running / paused
    config_changed = pyqtSignal()

    def _normalize_legacy_display_mode_config(self) -> None:
        """Deprecated: normalization runs in ConfigStore.__init__."""
        self.config._normalize_legacy_display_mode()

    def build_status_snapshot(self) -> dict[str, object]:
        return StatusSnapshotBuilder(self).build()

    def apply_web_config_payload(self, payload: dict[str, object]) -> None:
        ConfigService(self).apply_web_payload(payload)

    def __init__(self, web_launch_mode: str = "webview"):
        super().__init__()
        from app.startup_trace import log_startup

        log_startup("danmu_app.init.begin")
        init_started = time.perf_counter()
        # --- Web 桥接状态（FastAPI/uvicorn 在独立线程；改 Qt 对象须经 web_bridge 信号）---
        self.web_launch_mode = web_launch_mode
        self.web_server = None
        self.web_bridge = None
        self.webview_shell = None
        self.web_runtime_state = WebRuntimeState()
        self._region_selector = None
        self._region_selection_state = "idle"
        self._region_selection_screen_index: int | None = None
        # --- 核心子系统（配置、截图、弹幕引擎、叠加层、托盘、全局热键）---
        config_started = time.perf_counter()
        self.config = ConfigStore()
        log_startup(
            "config_store.done",
            ms=(time.perf_counter() - config_started) * 1000.0,
        )
        Translator.set_language(
            Translator.resolve_language(
                config_value_with_default(self.config, "language")
            )
        )
        self.logger = SanitizedLogger()
        self.personae = PersonaManager(self.config)
        self.templates = TemplateManager(self.config)
        self.history_writer = HistoryWriter(self.config)
        self.capturer = ScreenCapturer(self.config)
        self.engine = DanmuEngine(self.config)
        self.overlay = DanmuOverlay(self.config, self.engine)
        self.engine.overlay = self.overlay
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.focusChanged.connect(self._on_app_focus_changed)
        self.web_runtime_state.set_overlay_cache(
            danmu_lines=self.config.get_int("danmu_lines", 0),
            layout_mode=self.config.get("layout_mode", "fullscreen"),
        )
        tray_started = time.perf_counter()
        self.tray = TrayManager(self)
        log_startup("tray.done", ms=(time.perf_counter() - tray_started) * 1000.0)
        self.hotkey = HotkeyManager(self)

        # W-FP-002：悬浮窗本体（默认 display_mode=overlay 隐藏；W-FP-003 接入主链路分发）
        from app.floating_panel import FloatingPanel

        self.floating_panel = FloatingPanel(self.config)
        self.floating_panel.set_display_mode(
            config_value_with_default(self.config, "display_mode")
        )

        # --- 视觉 AI 请求与截图定时（MAX_IN_FLIGHT=1：并发会破坏过期与顺序判定）---
        self.ai_worker = AiWorker(self.config)
        self.ai_worker.finished.connect(self._on_ai_reply)
        self.ai_worker.error.connect(self._on_ai_error)

        self.screenshot_round = 0
        self.screenshot_timer = QTimer()
        self.screenshot_timer.timeout.connect(self._on_screenshot_timer)

        self.ai_in_flight = 0
        self.mic_in_flight = 0
        self._local_fallback_active = False
        self._mic_request_seq = 0
        self._mic_batch_id = 0
        self._pending_request_meta: dict[tuple[int, int, int], dict] = {}
        # --- 麦克风双轨（mic_in_flight 与视觉独立；负 request_round 区分 meta 来源）---
        self._mic_poll_timer = QTimer(self)
        self._mic_poll_ms = MIC_POLL_MS
        self._mic_poll_timer.setInterval(self._mic_poll_ms)
        self._mic_poll_timer.setSingleShot(True)
        self._mic_poll_timer.timeout.connect(self._poll_mic_utterance)

        # --- 最新帧与批次节拍（_is_generating=意图标记；ai_in_flight=在途计数，二者不同步混用）---
        self._latest_screenshot: QPixmap | None = None
        self._latest_screenshot_time: float = 0.0
        self._is_generating: bool = False
        self._batch_id: int = 0
        self._current_batch: BatchTracker | None = None

        # --- 回复 FIFO 与自适应消费（reply_timer 单次触发，按屏上密度调节间隔）---
        self.reply_buffer = AIReplyFIFOBuffer(max_items=8)
        self.reply_timer = QTimer(self)
        self.reply_timer.setInterval(800)
        self.reply_timer.setSingleShot(True)
        self.reply_timer.timeout.connect(self._consume_reply_queue)

        self._pool_topup_timer = QTimer(self)
        self._pool_topup_timer.setInterval(500)
        self._pool_topup_timer.timeout.connect(self._maybe_pool_topup)

        self._queue_low_watermark = 3
        self._queue_fallback_keep = 3
        self._reply_scene_count = 2
        self._reply_filler_count = 3
        self._queue_batch_size = 5

        # --- 场景代际与截图 ID 链（scene_generation 兼容字段；screenshot_id 单调递增）---
        self._pending = False
        self._latest_displayed_round = 0
        self._request_timing_service = RequestTimingService()
        self._scene_generation: int = 0
        self._inflight_scene_generation: int = 0
        self._latest_screenshot_id: int = 0
        self._latest_requested_screenshot_id: int = 0
        self._latest_queued_screenshot_id: int = 0
        self._latest_displayed_screenshot_id: int = 0
        # RequestScheduler / RequestTimingService：Phase 4 真实所有权；DanmuApp 仅保留 @property 兼容 façade
        self._request_scheduler = RequestScheduler()
        self._scene_memory = SceneMemoryStore()
        self._activity_state = RecentActivityState()
        self._last_activity_collect_at: float = 0.0
        self._mic_service = MicService(log_fn=lambda msg: self.logger.info(msg))
        self._mic_orchestrator = MicOrchestrator(
            mic_service=self._mic_service,
            on_utterance_end=self._on_mic_utterance_end,
            log_fn=lambda msg: self.logger.info(msg),
        )
        self._danmu_read_service = DanmuReadService(self)

        # --- 会话统计（Token/弹幕计数；stop/quit 时并入 LifetimeStats）---
        self.stats_state = StatsState()

        # 连续失败退避机制
        self._consecutive_failures = 0
        self._failure_backoff_paused = False
        self._last_error_message = ""
        self.MAX_CONSECUTIVE_FAILURES = 5

        self._inflight_screenshot_id: int = 0
        self._inflight_started_at: float = 0.0
        self._live_status_timer = QTimer(self)
        self._live_status_timer.setInterval(500)
        self._live_status_timer.timeout.connect(self._publish_live_status)

        self.tray.show()
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.processEvents()
        hotkey_started = time.perf_counter()
        try:
            self.hotkey.register()
        except Exception as exc:
            self.logger.error("热键注册失败: %r", exc)
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(None, tr("app.error_title"), f"热键注册失败: {exc}")
        log_startup(
            "hotkey.register.done",
            ms=(time.perf_counter() - hotkey_started) * 1000.0,
        )
        # legacy display mode normalized in ConfigStore.__init__

        # 统计数据（会话内 + 持久化累计）
        from app.session_run_log import SessionRunLog

        self.session_run_log = SessionRunLog(self.config)
        self.lifetime_stats = LifetimeStats(self.config)
        self._lifetime_flush_timer = QTimer(self)
        self._lifetime_flush_timer.setInterval(2000)
        self._lifetime_flush_timer.timeout.connect(self.lifetime_stats.flush_pending)

        from app.web_console import attach_web_console

        try:
            self.web_server = attach_web_console(self)
        except Exception as exc:
            self.logger.error("Web 控制台启动失败: %r", exc)
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(None, tr("app.error_title"), f"Web 控制台启动失败: {exc}")
            raise
        self.config_changed.connect(self._on_config_changed)
        initial = "/#settings" if not self.config.get_api_key() else "/"
        if self.web_server.startup_ok:
            self.logger.info(
                f"Web 控制台: {self.web_server.base_url} （托盘可再次打开）"
            )
        else:
            if self.web_launch_mode == "browser":
                self.logger.warning(
                    f"Web 控制台仍在启动: {self.web_server.base_url} "
                    "（就绪前将先打开系统浏览器）"
                )
            else:
                self.logger.warning(
                    f"Web 控制台仍在启动: {self.web_server.base_url} "
                    "（就绪后将打开桌面壳，请勿仅用浏览器替代）"
                )

        show_startup_notice_if_needed(self.config, self.logger)

        if self.web_launch_mode == "browser":
            QTimer.singleShot(
                900,
                lambda: self._open_web_console_when_ready(initial, use_browser=True),
            )
        else:
            self.logger.info(
                "桌面壳: pywebview（--web-browser 可改用系统浏览器）"
            )
            from app.web_console import classify_web_console_startup
            from app.webview_shell import notify_web_console_failure

            if classify_web_console_startup(self.web_server) == "failed":
                notify_web_console_failure(self, "web_console.startup_failed")
                self.web_server._startup_failure_user_notified = True
            else:
                self._schedule_webview_attach(initial)

        self._sync_reply_batch_config()
        log_startup(
            "danmu_app.init.end",
            ms=(time.perf_counter() - init_started) * 1000.0,
            startup_ok=bool(self.web_server and self.web_server.startup_ok),
        )

    def _on_config_changed(self):
        self._sync_reply_batch_config()
        web_runtime_state = self._ensure_web_runtime_state()
        self.screenshot_timer.setInterval(self._normal_recognition_interval_ms())
        self.reply_buffer.set_max_items(self._queue_capacity())
        new_lines = self.config.get_int("danmu_lines", 0)
        lines_changed = new_lines != web_runtime_state.cached_danmu_lines
        if lines_changed:
            self.engine.reload_tracks(preserve_visible=True)
        new_layout = self.config.get("layout_mode", "fullscreen")
        layout_changed = new_layout != web_runtime_state.cached_layout_mode
        if layout_changed:
            if self.engine.running:
                self.overlay.show_for_screen(
                    resolve_screen_index(self.config),
                    reload_tracks=True,
                )
        if lines_changed or layout_changed:
            web_runtime_state.set_overlay_cache(
                danmu_lines=new_lines,
                layout_mode=new_layout,
            )
        hotkey_str = self.config.get("hotkey", "Ctrl+Shift+B")
        self.hotkey.set_keys(hotkey_str)
        if self.overlay.display_settings_dirty():
            self.overlay.apply_display_settings()
        if self.engine.running:
            self.overlay.show_for_screen(resolve_screen_index(self.config))
            self.overlay.ensure_render_loop()
        self._sync_mic_service()
        # W-FP-003：悬浮窗配置热更新与显隐切换
        panel = self.__dict__.get("floating_panel")
        if panel is not None:
            try:
                panel.apply_config()
                panel.set_display_mode(self.config.get("display_mode", "overlay"))
            except Exception as exc:
                self.logger.debug(f"floating panel sync skipped: {exc!r}")

    def _mic_audio_supported(self) -> bool:
        return mic_audio_supported_for_mic_config(self.config)

    def _sync_mic_service(self) -> None:
        """按配置与运行状态启停 MicService / 端点检测器，避免保存配置时反复开关默认录音设备。

        关闭 mic 模式时才 stop 采集（蓝牙耳机在 Windows 上易因反复 open/close 断连）。
        弹幕未运行时仅预热或保持采集，utterance 检测在 engine.running 且模型支持音频后才启动。
        """
        self._mic_orchestrator.sync(
            engine_running=self.engine.running,
            config=self.config,
            mic_audio_supported_fn=self._mic_audio_supported,
            resolve_active_model_id_fn=lambda: resolve_mic_model_id(self.config),
        )
        if self._mic_orchestrator.detector is not None:
            self._mic_poll_timer.stop()
            self._mic_poll_timer.start(MIC_POLL_PHASE_MS)
            QTimer.singleShot(1500, self._calibrate_mic_noise_floor)
        else:
            self._mic_poll_timer.stop()

    def _calibrate_mic_noise_floor(self) -> None:
        self._mic_orchestrator.calibrate_noise_floor(
            engine_running=self.engine.running,
            config=self.config,
        )

    def _poll_mic_utterance(self) -> None:
        try:
            self._mic_orchestrator.poll(
                engine_running=self.engine.running,
                config=self.config,
            )
        finally:
            if self._mic_orchestrator.should_schedule_next_poll(
                engine_running=self.engine.running,
                config=self.config,
            ):
                self._mic_poll_timer.start(self._mic_poll_ms)

    def _on_mic_utterance_end(self) -> None:
        if not mic_mode_enabled(self.config) or not self.engine.running:
            return
        if self._has_mic_request_in_flight():
            self.logger.info("mic insert skipped: request already in flight")
            return
        if not self._mic_audio_supported():
            return
        pcm = self._mic_orchestrator.snapshot_pcm_for_utterance(self.config)
        if pcm is None:
            return
        rms, _ = self._mic_orchestrator.pcm_metrics(pcm)
        self.logger.info(
            f"mic utterance end: pcm_bytes={len(pcm)} rms={rms}"
        )
        self._trigger_mic_api_call(pcm)

    def _has_mic_request_in_flight(self) -> bool:
        return self.mic_in_flight >= MAX_MIC_IN_FLIGHT

    def _register_request_meta(
        self,
        request_round: int,
        screenshot_id: int,
        scene_generation: int,
        source: str,
    ) -> str:
        key = self._reply_request_id(request_round, screenshot_id, scene_generation)
        self._pending_request_meta[key] = {"source": source}
        return key

    def _pop_request_meta(
        self,
        request_round: int,
        screenshot_id: int,
        scene_generation: int,
    ) -> dict:
        key = self._reply_request_id(request_round, screenshot_id, scene_generation)
        meta = self._pending_request_meta.pop(key, None)
        if meta is None:
            self.logger.warning(
                "request_meta_missing: request_id=%s screenshot_id=%s request_round=%s "
                "scene_generation=%s reason=pop_before_reply",
                key,
                screenshot_id,
                request_round,
                scene_generation,
            )
            return {}
        return meta

    def _release_inflight_for_source(self, source: str) -> None:
        if source == "mic":
            self.mic_in_flight = max(0, self.mic_in_flight - 1)
            return
        self.ai_in_flight = max(0, self.ai_in_flight - 1)
        self._is_generating = False
        self._inflight_started_at = 0.0
        self._inflight_screenshot_id = 0
        self._inflight_scene_generation = 0

    def _trigger_mic_api_call(self, pcm: bytes) -> None:
        """语音段结束时插入一发 AI：附最新截图 + PCM，与视觉轨共享 AiWorker 但独立 mic_in_flight。

        request_round 取负递增（-_mic_request_seq），与视觉正 round 区分，防止 _pending_request_meta 混淆。
        """
        if not mic_mode_enabled(self.config) or not self.engine.running:
            return
        if self._has_mic_request_in_flight():
            return
        if not self._mic_audio_supported():
            model_id = resolve_mic_model_id(self.config)
            self.logger.warning(tr("mic.warn_unsupported_model").format(model=model_id or "?"))
            return
        if self._latest_screenshot is None:
            self.logger.debug("mic insert skipped: no_screenshot")
            return
        if not pcm or pcm_to_wav_data_uri(pcm) is None:
            self.logger.debug(tr("mic.warn_empty_buffer"))
            return

        self._mic_request_seq += 1
        request_round = -self._mic_request_seq
        screenshot_id = self._latest_screenshot_id
        captured_at = time.monotonic()
        scene_generation = self._scene_generation
        pixmap = self._latest_screenshot

        persona = self.personae.pick_random()
        system_pt, user_pt = self.personae.get_prompt(persona)
        system_pt = append_nickname_to_system_pt(system_pt, self.config)  # W-NICKNAME-001
        system_pt = append_live_topic_to_system_pt(system_pt, self.config)  # W-LIVE-TOPIC-001
        now = datetime.now().strftime("%H:%M:%S")
        user_pt = user_pt.replace("{current_time}", now)
        user_pt = user_pt.replace("{round}", str(self.screenshot_round))
        user_pt = build_mic_insert_user_pt(user_pt, self.config)

        self.mic_in_flight += 1
        mic_request_id = self._reply_request_id(request_round, screenshot_id, scene_generation)
        self._get_request_timing_service().mark_started(
            request_id=mic_request_id,
            now=time.monotonic(),
        )
        self._register_request_meta(request_round, screenshot_id, scene_generation, "mic")
        self.logger.info(
            f"mic insert api triggered seq={self._mic_request_seq} "
            f"screenshot_id={screenshot_id} pcm_bytes={len(pcm)}"
        )

        from app.runnable import AiRunnable
        from PyQt6.QtCore import QThreadPool

        image_max_width = self.config.get_int("image_max_width", IMAGE_MAX_WIDTH)
        image_quality = self.config.get_int("image_quality", IMAGE_JPEG_QUALITY)
        runnable = AiRunnable(
            self.ai_worker,
            pixmap,
            system_pt,
            user_pt,
            persona,
            request_round,
            screenshot_id,
            captured_at,
            scene_generation,
            lambda p: compress_screenshot(p, image_max_width, image_quality),
            image_quality=image_quality,
            mic_pcm=pcm,
            mic_attach_audio=True,
        )
        QThreadPool.globalInstance().start(runnable)

    def _has_visual_request_in_flight(self) -> bool:
        return self._is_generating or self.ai_in_flight >= MAX_IN_FLIGHT

    def _current_danmu_delay_sec(self) -> float:
        from app.application.live_status_projection import current_danmu_delay_sec

        return current_danmu_delay_sec(
            has_visual_request_in_flight=self._has_visual_request_in_flight(),
            inflight_started_at=self._inflight_started_at,
            reply_buffer=self.reply_buffer,
            latest_screenshot_time=self._latest_screenshot_time,
        )

    def _build_live_status_snapshot(self) -> LiveStatusSnapshot:
        from app.application.live_status_projection import build_live_status_snapshot

        return build_live_status_snapshot(
            has_visual_request_in_flight=self._has_visual_request_in_flight(),
            inflight_started_at=self._inflight_started_at,
            reply_buffer=self.reply_buffer,
            latest_screenshot_time=self._latest_screenshot_time,
            local_fallback=self._local_fallback_active,
        )

    def _maybe_inject_local_fallback(self) -> None:
        """慢模型 in-flight 时注入公式化弹幕库轻量批次，避免长时间空窗。"""
        if not self.engine.running or self._local_fallback_active:
            return
        if not self._has_visual_request_in_flight():
            return
        inflight_elapsed = 0.0
        if self._inflight_started_at > 0:
            inflight_elapsed = time.monotonic() - self._inflight_started_at
        if not is_model_slow(
            self._get_request_timing_service().rtt_history,
            inflight_elapsed,
            in_flight=True,
        ):
            return
        normalized_items = build_local_fallback_batch(config=self.config)
        if not normalized_items:
            return
        captured_at = self._latest_screenshot_time or time.monotonic()
        self._enqueue_reply_batch(
            "本地兜底",
            self.screenshot_round,
            self._inflight_screenshot_id,
            captured_at,
            self._inflight_scene_generation,
            normalized_items,
            from_local_fallback=True,
        )
        self._local_fallback_active = True
        if not self.reply_timer.isActive():
            self._consume_reply_queue()
        elif not self.reply_buffer.is_empty():
            self.reply_timer.setInterval(min(self.reply_timer.interval(), 200))
        self._publish_live_status()

    def _publish_live_status(self):
        if not self.engine.running:
            return
        bridge = getattr(self, "web_bridge", None)
        if bridge:
            bridge.publish_status()

    def _api_schedule_block_reason(self, *, enforce_min_interval: bool) -> str:
        """委托 RequestScheduler 判断视觉请求是否应阻塞；不发起 HTTP、不改队列。

        返回非空字符串时 _trigger_api_call 直接 return（如 in_flight、min_api_interval）。
        """
        scheduler = self._get_request_scheduler()
        return scheduler.block_reason(
            has_visual_request_in_flight=self._has_visual_request_in_flight(),
            enforce_min_interval=enforce_min_interval,
            last_trigger_at=scheduler.last_api_trigger_at,
            min_interval_elapsed=min_api_interval_elapsed,
        )

    def _log_api_schedule(
        self,
        *,
        decision: str,
        source: str,
        block_reason: str = "",
    ) -> None:
        from app.main_helpers import log_api_schedule

        log_api_schedule(
            self.logger,
            decision=decision,
            source=source,
            block_reason=block_reason,
            batch=self._current_batch,
            rtt_avg=self._rtt_avg(),
            buffer_size=self.reply_buffer.size(),
            visible_count=self._visible_display_count(),
            in_flight=self._has_visual_request_in_flight(),
            scene_gen=self._scene_generation,
        )

    def _consume_request_timing(
        self,
        request_round: int,
        screenshot_id: int,
        scene_generation: int,
    ) -> None:
        request_id = self._reply_request_id(request_round, screenshot_id, scene_generation)
        timing_service = self._get_request_timing_service()
        rtt = timing_service.consume_timing(
            request_id=request_id,
            now=time.monotonic(),
        )
        if rtt is None:
            self.logger.warning(
                "RTT 样本缺失: request_id=%s screenshot_id=%s request_round=%s "
                "scene_generation=%s reason=timing_not_started",
                request_id,
                screenshot_id,
                request_round,
                scene_generation,
            )
            return
        self.logger.debug(
            f"[DEBUG] RTT={rtt:.1f}s, avg={self._rtt_avg():.1f}s, request_id={request_id}"
        )

    def _memory_tone_hint(self, persona_id: str) -> str:
        return memory_tone_hint(persona_id)

    def _memory_mode(self) -> str:
        return memory_mode_from_value(self.config.get("memory_mode", MEMORY_MODE_OFF))

    def _memory_enabled(self) -> bool:
        return memory_enabled(self._memory_mode())

    def _collect_activity_observation(self) -> None:
        if not self._memory_enabled():
            return
        now = time.monotonic()
        if now - self._last_activity_collect_at < 1.0:
            return
        self._last_activity_collect_at = now
        try:
            info = get_foreground_window_info()
            if info is None:
                return
            obs = classify_foreground_window(info.title, info.exe_name)
            obs.scene_generation = self._scene_generation
            self._activity_state.record_observation(obs)
        except Exception:
            pass

    def _append_scene_memory_to_user_pt(self, user_pt: str) -> str:
        mode = self._memory_mode()
        if mode == MEMORY_MODE_OFF:
            return user_pt
        activity_line = format_activity_prompt_line(self._activity_state)
        if activity_line:
            return append_activity_line_to_user_pt(user_pt, activity_line)
        block = self._scene_memory.format_prompt_for_generation(self._scene_generation, mode)
        return append_memory_to_user_pt(user_pt, block)

    def _record_scene_memory_display(self, queued: QueuedReply) -> None:
        if not self._memory_enabled():
            return
        if not queued.memory_eligible or queued.is_fallback or queued.source not in ("ai", "mic"):
            return
        angle = bullet_angle_from_index(queued.content_index, self._reply_scene_count)
        self._scene_memory.record_displayed_bullet(
            queued.content,
            queued.scene_generation,
            window=memory_window_from_config(self.config),
            angle=angle,
        )
        if not self._scene_memory.context.tone_hint:
            hint = self._memory_tone_hint(queued.persona_id)
            if hint:
                self._scene_memory.context.tone_hint = hint

    def _queue_capacity(self) -> int:
        return queue_capacity(self.config, self._normal_reply_count())

    def _reply_request_id(self, request_round: int, screenshot_id: int, scene_generation: int) -> str:
        return reply_request_id(request_round, screenshot_id, scene_generation)

    def _min_density_target(self) -> int:
        return self.engine.min_on_screen()

    def _density_right_target(self, min_n: int) -> int:
        return density_right_target(min_n)

    def _maybe_pool_topup(self) -> int:
        from app.danmu_pool import maybe_pool_topup

        return maybe_pool_topup(self.engine, self.config, self._scene_generation)

    def _estimated_reply_gap_ms(self) -> int:
        if self.reply_timer.isActive():
            current_interval = self.reply_timer.interval()
            if current_interval > 0:
                return current_interval

        if hasattr(self.engine, "visibility_counts"):
            visible_total, right_count = self.engine.visibility_counts()
        else:
            visible_total = self._visible_display_count()
            right_count = self._right_visible_count()
        min_n = self._min_density_target()
        right_target = self._density_right_target(min_n)
        if min_n > 0 and visible_total < min_n:
            return 200
        if visible_total == 0:
            return 120
        if min_n > 0 and visible_total >= min_n and right_count >= right_target:
            return 1000
        if right_count >= right_target:
            return 1000
        if right_count > 0:
            return 500
        return 200

    def _capture_screenshot(self):
        if not self.engine.running:
            return
        if self._failure_backoff_paused:
            return
        pixmap = self.capturer.grab()
        if pixmap is None:
            self.logger.warning(tr("app.capture_failed"))
            return
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            screen_index = self.config.get_int("screen_index", 0)
            region_x = self.config.get_int("region_x", 0)
            region_y = self.config.get_int("region_y", 0)
            region_w = self.config.get_int("region_w", 0)
            region_h = self.config.get_int("region_h", 0)
            self.logger.warning(
                "截图无效: is_null=%s width=%s height=%s screen_index=%s "
                "region_x=%s region_y=%s region_w=%s region_h=%s reason=invalid_pixmap",
                pixmap.isNull(),
                pixmap.width(),
                pixmap.height(),
                screen_index,
                region_x,
                region_y,
                region_w,
                region_h,
            )
            return
        self._latest_screenshot = pixmap
        self._latest_screenshot_time = time.monotonic()
        self._latest_screenshot_id += 1
        self.logger.debug(
            tr("app.screenshot_updated").format(
                screenshot_id=self._latest_screenshot_id,
                scene_generation=self._scene_generation,
                width=pixmap.width(),
                height=pixmap.height(),
            )
        )
        self._collect_activity_observation()

    def _on_screenshot_timer(self):
        self._on_normal_capture_tick()

    def _on_normal_capture_tick(self):
        # 普通模式主链路：无视觉 in-flight 才截图；成功则同 tick 内触发 API（不等待 reply_timer）
        if self._has_visual_request_in_flight():
            elapsed_ms = 0
            if self._inflight_started_at > 0:
                elapsed_ms = int((time.monotonic() - self._inflight_started_at) * 1000)
            warn_ms = int(VISUAL_INFLIGHT_WARN_SEC * 1000)
            if elapsed_ms >= warn_ms:
                self.logger.warning(
                    "视觉请求 in-flight 超时: screenshot_id=%s elapsed_ms=%s ai_in_flight=%s "
                    "reason=inflight_watchdog",
                    self._inflight_screenshot_id,
                    elapsed_ms,
                    self.ai_in_flight,
                )
            else:
                self.logger.debug(
                    "跳过截图 tick: reason=in_flight screenshot_id=%s elapsed_ms=%s",
                    self._inflight_screenshot_id,
                    elapsed_ms,
                )
            self._maybe_inject_local_fallback()
            return
        self._capture_screenshot()
        if self._latest_screenshot is None:
            return
        self._trigger_api_call(source="normal_interval")

    def _trigger_api_call(self, source: str = "unknown"):
        """占用唯一视觉 in-flight 槽位，用当前 _latest_screenshot 发起 AiRunnable。

        递增 screenshot_round / _batch_id，登记 _inflight_* 与 _pending_request_meta 供回复到达时
        做过期判断；成功触发后清除 local_fallback 标记，避免与真 AI 回复重复占位。
        """
        block = self._api_schedule_block_reason(enforce_min_interval=True)
        if block:
            self._log_api_schedule(decision="block", source=source, block_reason=block)
            if block == "in_flight":
                self.logger.debug(tr("app.skip_api_generating"))
            return
        if self.ai_in_flight >= MAX_IN_FLIGHT:
            self._log_api_schedule(decision="block", source=source, block_reason="in_flight")
            self.logger.debug(tr("app.skip_api_generating"))
            return
        if self._latest_screenshot is None:
            self._log_api_schedule(decision="block", source=source, block_reason="no_screenshot")
            self.logger.debug(tr("app.skip_api_no_screenshot"))
            return

        trigger_at = time.monotonic()
        self._local_fallback_active = False
        self._get_request_scheduler().record_trigger_time(now=trigger_at)
        self._log_api_schedule(decision="fire", source=source)
        pixmap = self._latest_screenshot
        self._is_generating = True
        self.ai_in_flight += 1
        self.screenshot_round += 1
        request_round = self.screenshot_round
        screenshot_id = self._latest_screenshot_id
        captured_at = self._latest_screenshot_time
        self._batch_id += 1
        batch_id = self._batch_id
        self._latest_requested_screenshot_id = screenshot_id
        self._inflight_screenshot_id = screenshot_id
        self._inflight_scene_generation = self._scene_generation
        self._inflight_started_at = time.monotonic()
        self._publish_live_status()

        persona = self.personae.pick_random()
        system_pt, user_pt = self.personae.get_prompt(persona)
        system_pt = append_nickname_to_system_pt(system_pt, self.config)  # W-NICKNAME-001
        system_pt = append_live_topic_to_system_pt(system_pt, self.config)  # W-LIVE-TOPIC-001

        request_id = self._reply_request_id(request_round, screenshot_id, self._scene_generation)
        self.logger.info(
            tr("app.api_triggered").format(
                batch_id=batch_id,
                screenshot_id=screenshot_id,
                scene_generation=self._scene_generation,
                persona=persona_display_name(persona),
            )
            + f" request_round={request_round} request_id={request_id}"
        )

        now = datetime.now().strftime("%H:%M:%S")
        user_pt = user_pt.replace("{current_time}", now)
        user_pt = user_pt.replace("{round}", str(self.screenshot_round))
        user_pt = self._append_scene_memory_to_user_pt(user_pt)

        self._current_persona = persona
        self._get_request_timing_service().mark_started(
            request_id=request_id,
            now=time.monotonic(),
        )
        self._register_request_meta(request_round, screenshot_id, self._scene_generation, "visual")

        from app.runnable import AiRunnable
        from PyQt6.QtCore import QThreadPool

        image_max_width = self.config.get_int("image_max_width", IMAGE_MAX_WIDTH)
        image_quality = self.config.get_int("image_quality", IMAGE_JPEG_QUALITY)
        runnable = AiRunnable(
            self.ai_worker,
            pixmap,
            system_pt,
            user_pt,
            persona,
            request_round,
            screenshot_id,
            captured_at,
            self._scene_generation,
            lambda p: compress_screenshot(p, image_max_width, image_quality),
            image_quality=image_quality,
        )
        QThreadPool.globalInstance().start(runnable)

    def _danmu_pixels_per_second(self, speed: float | None = None) -> float:
        if speed is None:
            from app.config_defaults import DEFAULT_DANMU_SPEED

            speed = self.config.get_float("danmu_speed", DEFAULT_DANMU_SPEED)
        factor = 1.0
        if getattr(self.engine, "_accel_remaining", 0) > 0:
            factor = min(getattr(self.engine, "_accel_peak", 1.0), 2.0)
        return pixels_per_second(speed, factor)

    def _default_batch_interval(self) -> float:
        from app.config_defaults import DEFAULT_DANMU_SPEED

        speed = self.config.get_float("danmu_speed", DEFAULT_DANMU_SPEED)
        speed_per_second = self._danmu_pixels_per_second(speed)
        if speed_per_second <= 0:
            return 5.0
        distance = self.engine.screen_width * 0.25
        return distance / speed_per_second

    def _reply_low_watermark(self) -> int:
        return max(0, self.config.get_int("reply_low_watermark", 1))

    def _empty_accel_enabled(self) -> bool:
        return self.config.get("empty_accel", "1") == "1"

    def _visible_display_count(self) -> int:
        if hasattr(self.engine, "visible_display_count"):
            return self.engine.visible_display_count()
        return self.engine.current_display_count()

    def _right_visible_count(self) -> int:
        if hasattr(self.engine, "right_visible_count"):
            return self.engine.right_visible_count()
        return self.engine.right_zone_count()

    def _broadcast_live_overlay_item(self, item, text: str, *, source: str) -> None:
        """Qt 上屏后旁路同步单条弹幕到网页层（含轨道 Y，与 Overlay 对齐）。"""
        state = getattr(self, "__dict__", None) or {}
        server = state.get("web_server")
        hub = getattr(server, "live_overlay_hub", None) if server else None
        if not hub or not text:
            return
        try:
            hub.broadcast_item(
                text,
                y=float(item.y),
                screen_width=float(self.engine.screen_width),
                screen_height=float(self.engine.screen_height),
                speed=float(item.speed),
                source=source,
            )
        except Exception as exc:
            self.logger.debug(f"live overlay broadcast skipped: {exc!r}")

    # W-FP-003：悬浮窗旁路分发（_consume_reply_queue 上屏后调用）
    def _floating_panel_enabled(self) -> bool:
        mode = (self.config.get("display_mode", "overlay") or "overlay").strip().lower()
        return mode in ("floating_panel", "both")

    def _feed_floating_panel(self, content: str, persona_id: str) -> None:
        if not content:
            return
        panel = self.__dict__.get("floating_panel")
        if panel is None:
            return
        if not self._floating_panel_enabled():
            return
        try:
            panel.feed(content, persona_id or "")
        except Exception as exc:  # 悬浮窗是消费者，绝不阻断主链路
            self.logger.debug(f"floating panel feed skipped: {exc!r}")

    def inject_test_danmu_batch(self, items: list[str], *, persona_id: str = "测试") -> dict[str, object]:
        """主线程测试入口：按正常 reply -> overlay -> history 链路注入一批弹幕。"""
        normalized_items = [str(item).strip() for item in items if str(item).strip()]
        if not normalized_items:
            raise ValueError("请至少提供一条弹幕")
        if len(normalized_items) > 20:
            raise ValueError("单次最多注入 20 条弹幕")

        request_round = max(int(getattr(self, "screenshot_round", 0)), 0)
        latest_screenshot_id = max(
            int(getattr(self, "_latest_screenshot_id", 0)),
            int(getattr(self, "_latest_queued_screenshot_id", 0)),
            int(getattr(self, "_latest_displayed_screenshot_id", 0)),
            1,
        )
        scene_generation = int(getattr(self, "_scene_generation", 0))
        captured_at = time.monotonic()

        self._batch_id += 1
        batch_id = self._batch_id
        request_id = self._reply_request_id(request_round, latest_screenshot_id, scene_generation)
        batch_items = [
            QueuedReply(
                persona_id,
                request_round,
                content_index,
                item_text,
                screenshot_round=request_round,
                screenshot_id=latest_screenshot_id,
                captured_at=captured_at,
                scene_generation=scene_generation,
                batch_id=batch_id,
                request_id=request_id,
                source="test",
                memory_eligible=False,
            )
            for content_index, item_text in enumerate(normalized_items)
        ]

        self._latest_queued_screenshot_id = max(self._latest_queued_screenshot_id, latest_screenshot_id)
        self.reply_buffer.extend(batch_items)
        self._publish_live_status()

        if not self.reply_timer.isActive():
            self._consume_reply_queue()
        elif self.reply_buffer.size() > self._queue_low_watermark:
            self.reply_timer.stop()
            self._consume_reply_queue()
        else:
            self.reply_timer.setInterval(min(self.reply_timer.interval(), 200))

        expected_texts = [
            normalize_danmu_display_text(item_text, self.config) for item_text in normalized_items
        ]
        visible_texts = []
        if hasattr(self.engine, "visible_display_texts"):
            visible_texts = list(self.engine.visible_display_texts())
        active_texts = []
        tracks = getattr(self.engine, "tracks", None)
        if tracks:
            for track in tracks:
                for item in getattr(track, "items", []):
                    active_texts.append(item.content)

        return {
            "ok": True,
            "queued": len(batch_items),
            "screenshot_id": latest_screenshot_id,
            "expected_texts": expected_texts,
            "visible_texts": visible_texts,
            "active_texts": active_texts,
        }

    def _enqueue_reply_batch(
        self,
        persona_id: str,
        request_round: int,
        screenshot_id: int,
        captured_at: float,
        scene_generation: int,
        normalized_items: list[str],
        *,
        from_local_fallback: bool = False,
        from_mic_insert: bool = False,
    ):
        """构造 QueuedReply 批次写入 reply_buffer；副作用：更新 _latest_queued_screenshot_id。

        普通视觉批次走 extend（队尾）；mic / local_fallback 走 prepend_batch（队首优先）。
        不在此调用 engine.add_text——上屏仅由 _consume_reply_queue 串行完成。
        """
        request_id = self._reply_request_id(request_round, screenshot_id, scene_generation)
        if from_mic_insert:
            self._mic_batch_id += 1
            batch_id = self._mic_batch_id
        else:
            batch_id = self._batch_id
        if from_mic_insert:
            source = "mic"
            replaceable = False
            memory_eligible = True
            is_fallback = False
        elif from_local_fallback:
            source = "fallback"
            replaceable = True
            memory_eligible = False
            is_fallback = True
        else:
            source = "ai"
            replaceable = False
            memory_eligible = True
            is_fallback = False

        batch_items = [
            QueuedReply(
                persona_id,
                request_round,
                content_index,
                item_text,
                screenshot_round=request_round,
                screenshot_id=screenshot_id,
                captured_at=captured_at,
                scene_generation=scene_generation,
                batch_id=batch_id,
                request_id=request_id,
                is_fallback=is_fallback,
                source=source,
                replaceable=replaceable,
                memory_eligible=memory_eligible,
            )
            for content_index, item_text in enumerate(normalized_items)
        ]

        if not from_mic_insert:
            self._latest_queued_screenshot_id = max(self._latest_queued_screenshot_id, screenshot_id)
        if from_mic_insert or from_local_fallback:
            self.reply_buffer.prepend_batch(
                batch_items,
                preserve_existing=self._queue_fallback_keep,
                preserve_scene_generation=scene_generation,
                preserve_replaceable=from_local_fallback,
            )
        else:
            self.reply_buffer.extend(batch_items)

        if from_local_fallback:
            self.logger.info(tr("app.local_fallback_batch").format(count=len(normalized_items)))
        elif from_mic_insert:
            self.logger.info(f"mic insert batch: count={len(normalized_items)} batch_id={batch_id}")
        else:
            self.logger.info(
                tr("app.batch_created").format(
                    batch_id=self._batch_id,
                    count=len(normalized_items),
                    interval=self._default_batch_interval(),
                )
            )

    def _on_ai_reply(self, text: str, persona_id: str, request_round: int, screenshot_id: int, captured_at: float, scene_generation: int, input_tokens: int = 0, output_tokens: int = 0):
        """AiWorker.finished 主线程入口：释放在途 → 解析入队 → 驱动 _consume_reply_queue。"""
        self.logger.debug(f"[DEBUG] _on_ai_reply called, text length={len(text)}")
        meta = self._pop_request_meta(request_round, screenshot_id, scene_generation)
        source = meta.get("source") or "visual"
        is_mic = source == "mic"

        self._release_inflight_for_source(source)

        stats_state = self._ensure_stats_state()
        stats_state.add_tokens(input_tokens, output_tokens)
        self.lifetime_stats.add_tokens(input_tokens, output_tokens)
        if input_tokens > 0 or output_tokens > 0:
            self.logger.debug(
                f"[DEBUG] Tokens: input={input_tokens}, output={output_tokens}, "
                f"total_input={stats_state.total_input_tokens}, total_output={stats_state.total_output_tokens}"
            )

        if is_mic:
            self._handle_mic_ai_reply(
                text,
                persona_id,
                request_round,
                screenshot_id,
                captured_at,
                scene_generation,
            )
            return

        if self._consecutive_failures > 0:
            self._consecutive_failures = 0
            self._last_error_message = ""
            if self._failure_backoff_paused:
                self._failure_backoff_paused = False
                self._set_error_status_safe("", is_error=False)
                if self.engine.running and not self.screenshot_timer.isActive():
                    self.screenshot_timer.start()

        self._consume_request_timing(request_round, screenshot_id, scene_generation)

        raw_items, memory_update = parse_ai_reply_with_memory(text, scene_generation)
        normalized_items = normalize_reply_batch(
            raw_items,
            scene_count=self._reply_scene_count,
            filler_count=self._reply_filler_count,
            config=self.config,
        )
        if not normalized_items:
            request_id = self._reply_request_id(request_round, screenshot_id, scene_generation)
            self.logger.warning(
                "AI 回复解析为空: request_id=%s screenshot_id=%s request_round=%s "
                "scene_generation=%s text_len=%s raw_count=%s reason=empty_parse",
                request_id,
                screenshot_id,
                request_round,
                scene_generation,
                len(text or ""),
                len(raw_items),
            )
            return

        if self._memory_enabled():
            if memory_update is not None:
                if memory_update.scene_generation <= 0:
                    memory_update.scene_generation = scene_generation
                self._scene_memory.update_from_visual_result(memory_update)

        self._enqueue_reply_batch(
            persona_id,
            request_round,
            screenshot_id,
            captured_at,
            scene_generation,
            normalized_items,
            from_local_fallback=False,
        )
        self._publish_live_status()

        if not self.reply_timer.isActive():
            self._consume_reply_queue()
        elif self.reply_buffer.size() > self._queue_low_watermark:
            self.reply_timer.stop()
            self._consume_reply_queue()
        else:
            self.reply_timer.setInterval(min(self.reply_timer.interval(), 200))

    def _handle_mic_ai_reply(
        self,
        text: str,
        persona_id: str,
        request_round: int,
        screenshot_id: int,
        captured_at: float,
        scene_generation: int,
    ) -> None:
        raw_items, memory_update = parse_ai_reply_with_memory(text, scene_generation)
        normalized_items = normalize_reply_batch(
            raw_items,
            scene_count=self._reply_scene_count,
            filler_count=self._reply_filler_count,
            config=self.config,
        )
        if not normalized_items:
            self.logger.debug("mic insert reply empty after parse")
            return

        if self._memory_enabled():
            if memory_update is not None:
                if memory_update.scene_generation <= 0:
                    memory_update.scene_generation = scene_generation
                self._scene_memory.update_from_visual_result(memory_update)

        self._enqueue_reply_batch(
            persona_id,
            request_round,
            screenshot_id,
            captured_at,
            scene_generation,
            normalized_items,
            from_mic_insert=True,
        )
        self._publish_live_status()
        if not self.reply_timer.isActive():
            self._consume_reply_queue()
        else:
            self.reply_timer.stop()
            self._consume_reply_queue()

    def _consume_reply_queue(self):
        """从 FIFO 弹出一条回复上屏；成功时更新 BatchTracker 锚点与 next_generation_time。

        fallback/mic 可 skip_dedup。
        锚点弹幕滚到 75% 屏宽处的时间写入 batch.next_generation_time（debug/批次元数据）。
        拒因（去重/入口过载）不入历史。
        """
        queued = self.reply_buffer.pop()
        if queued is None:
            return

        self.logger.info(f"[{persona_display_name(queued.persona_id)}] {queued.content}")
        display_content = normalize_danmu_display_text(queued.content, self.config)
        skip_dedup = queued.is_fallback or queued.source == "fallback"
        item = self.engine.add_text(
            queued.content,
            queued.persona_id,
            batch_id=queued.batch_id,
            scene_generation=queued.scene_generation,
            skip_dedup=skip_dedup,
        )
        if item:
            self._latest_displayed_round = max(self._latest_displayed_round, queued.screenshot_round)
            self._latest_displayed_screenshot_id = max(self._latest_displayed_screenshot_id, queued.screenshot_id)
            self.history_writer.enqueue(display_content, queued.persona_id, queued.batch_index)
            self._record_scene_memory_display(queued)
            overlay_source = queued.source if queued.source in ("ai", "mic", "test") else "ai"
            self._broadcast_live_overlay_item(item, display_content, source=overlay_source)
            # W-FP-003：悬浮窗旁路分发（不重发 AI、不影响主链路）
            self._feed_floating_panel(display_content, queued.persona_id)

            batch = self._current_batch
            if batch and batch.anchor_item is None and item.batch_id == batch.batch_id:
                batch.anchor_item = item
                target_x = self.engine.screen_width * 0.75
                distance = item.x - target_x
                if distance > 0 and item.speed > 0:
                    factor = 1.0
                    if getattr(self.engine, "_accel_remaining", 0) > 0:
                        factor = min(getattr(self.engine, "_accel_peak", 1.0), 2.0)
                    time_to_boundary = time_to_anchor_boundary(
                        distance, item.speed, factor
                    )
                    batch.next_generation_time = time.monotonic() + time_to_boundary
                    self.logger.info(
                        tr("app.batch_anchor").format(
                            batch_id=batch.batch_id,
                            x=item.x,
                            target_x=target_x,
                            time_to_boundary=time_to_boundary,
                        )
                    )
                else:
                    batch.next_generation_time = time.monotonic()
        else:
            if (not skip_dedup) and self.engine.is_duplicate(display_content):
                reject = "去重"
            elif self.engine.entry_zone_overloaded():
                reject = "入口区过载"
            else:
                reject = "轨道/布局"
            self.logger.info(
                tr("app.danmu_not_entered").format(content=f"{queued.content[:20]}...")
                + f" [{reject}]"
            )

        if not self.reply_buffer.is_empty():
            delay = 100 if item is None else self._estimated_reply_gap_ms()
            self.reply_timer.start(delay)

        self._update_stats(success=item is not None)
        self._maybe_pool_topup()

    def _rtt_avg(self) -> float:
        return self._get_request_timing_service().avg_rtt()

    def _smart_cooldown_ms(self) -> int:
        return self._get_request_timing_service().smart_cooldown_ms(
            fallback_interval_sec=self.config.get_int("screenshot_interval", 3),
        )

    def _on_ai_error(self, msg: str, persona_id: str, request_round: int, screenshot_id: int, captured_at: float, scene_generation: int, input_tokens: int = 0, output_tokens: int = 0):
        """AiWorker.error 主线程入口：释放在途、累计失败；401/403/余额等 fatal 时停截图定时器。

        与 _on_ai_reply 对称释放 _pending_request_meta；连续失败达阈值进入 _failure_backoff_paused。
        不在此解析弹幕或入队。
        """
        meta = self._pop_request_meta(request_round, screenshot_id, scene_generation)
        source = meta.get("source") or "visual"
        is_mic = source == "mic"

        self._release_inflight_for_source(source)
        self._publish_live_status()

        if is_mic:
            self.logger.warning(
                f"mic insert api error: {msg} "
                f"[persona={persona_id}, round={request_round}, screenshot_id={screenshot_id}]"
            )
            self._consume_request_timing(request_round, screenshot_id, scene_generation)
            return

        self._consume_request_timing(request_round, screenshot_id, scene_generation)
        self.logger.error(
            "%s [persona=%s, round=%s, screenshot_id=%s, scene_generation=%s, "
            "input_tokens=%s, output_tokens=%s]",
            msg, persona_id, request_round, screenshot_id, scene_generation,
            input_tokens, output_tokens,
        )

        self._consecutive_failures += 1
        self._last_error_message = msg

        lower_msg = msg.lower()
        is_fatal = (
            "401" in msg
            or "403" in msg
            or "api key" in lower_msg
            or "not configured" in lower_msg
            or "未配置" in msg
            or "余额" in msg
            or "balance" in lower_msg
            or "欠费" in msg
        )

        self._set_error_status_safe(msg, is_error=True)

        if is_fatal:
            self.logger.warning(tr("app.fatal_error_pause").format(message=msg))
            self._failure_backoff_paused = True
            self.screenshot_timer.stop()
            return

        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self.logger.warning(
                tr("app.failure_paused").format(count=self._consecutive_failures, message=msg)
            )
            self._failure_backoff_paused = True
            self.screenshot_timer.stop()
            self._set_error_status_safe(
                tr("app.failure_paused").format(count=self.MAX_CONSECUTIVE_FAILURES, message=msg),
                is_error=True
            )
            return

    def _maybe_log_dedup_profile(self) -> None:
        if not dedup_profile_enabled():
            return
        every = 25
        try:
            last_at = int(self._dedup_profile_log_at_count)
        except (AttributeError, RuntimeError):
            last_at = 0
        if self.danmu_count - last_at < every:
            return
        try:
            self._dedup_profile_log_at_count = self.danmu_count
        except RuntimeError:
            object.__setattr__(self, "_dedup_profile_log_at_count", self.danmu_count)
        log_dedup_profile_summary(self.logger)

    def _update_stats(self, *, success: bool = True):
        if success:
            self._ensure_stats_state().add_danmu(1)
            self.lifetime_stats.add_danmu(1)
        self._maybe_log_dedup_profile()

    def start(self):
        """开始一轮会话：清零代际/在途/队列/统计，启动 screenshot_timer 与 reply_timer，显示 Overlay。

        必须完整重置 start() 内列出的状态，遗漏会导致 stop 后再 start 沿用旧 scene_generation 或
        陈旧 in-flight 元数据。eviction_mode=accelerate 时触发引擎加速清空旧弹幕。
        """
        if not self.config.get_api_key():
            msg = tr("app.api_key_missing_warning")
            self.logger.warning(msg)
            self._set_error_status_safe(msg, is_error=True)
            self.tray.show_api_key_missing_hint()
            if self.web_server:
                self._open_web_console("/#settings")
            return
        self.engine.start()
        self.engine.clear_dedup_window()
        self.ai_worker.reset_stopping()
        self.ai_in_flight = 0
        self._is_generating = False
        self._local_fallback_active = False
        self._batch_id = 0
        self._current_batch = None
        self._latest_screenshot = None
        self._latest_screenshot_time = 0.0
        self._ensure_stats_state().reset_session(start_time=time.monotonic())
        self.session_run_log.begin(
            started_at=time.time(),
            model=resolve_active_model_id(self.config),
        )
        self._consecutive_failures = 0
        self._failure_backoff_paused = False
        self._last_error_message = ""
        self._get_request_timing_service().reset_started()
        self._latest_queued_screenshot_id = 0
        self._latest_displayed_screenshot_id = 0
        self._latest_requested_screenshot_id = 0
        self._scene_generation = 0
        self._inflight_scene_generation = 0
        self._inflight_started_at = 0.0
        self._inflight_screenshot_id = 0
        self._get_request_scheduler().reset_trigger_time()
        self._mic_request_seq = 0
        self._mic_batch_id = 0
        self._pending_request_meta.clear()
        self._scene_memory.reset()
        self._activity_state.reset()
        self._last_activity_collect_at = 0.0
        self.reply_buffer.set_max_items(self._queue_capacity())
        self.screenshot_timer.stop()
        self.screenshot_timer.setInterval(self._normal_recognition_interval_ms())
        self.screenshot_timer.start()
        self._live_status_timer.start()
        self._lifetime_flush_timer.start()
        self._on_normal_capture_tick()
        self.logger.debug(
            f"[DEBUG] Normal mode: screenshot={self._normal_recognition_interval_ms()}ms"
        )
        if not self.reply_buffer.is_empty() and not self.reply_timer.isActive():
            self.reply_timer.start(200)
        eviction = self.config.get("eviction_mode", "natural")
        if eviction == "accelerate":
            self.engine.trigger_acceleration(60)
        self.overlay.show_for_screen(resolve_screen_index(self.config))
        self.overlay.ensure_render_loop()
        self._pool_topup_timer.start()
        self.tray.update_state(running=True)
        self.state_changed.emit(True)
        self._set_error_status_safe("", is_error=False)
        self.logger.info(tr("app.started"))
        self._sync_mic_service()
        read_svc = self.__dict__.get("_danmu_read_service")
        if read_svc is not None:
            read_svc.on_engine_started()

    def apply_danmu_read_config(self, patch: dict) -> dict:
        """读弹幕配置（Web PUT /api/danmu-read/config）；须在主线程调用。"""
        return self._danmu_read_service.apply_config(patch)

    def run_danmu_read_probe(
        self,
        api_key_override: str | None = None,
        *,
        provider_override: str | None = None,
        endpoint_override: str | None = None,
        model_id_override: str | None = None,
    ) -> dict:
        """TTS 试听；须在主线程调用。"""
        return self._danmu_read_service.run_probe(
            api_key_override=api_key_override,
            provider_override=provider_override,
            endpoint_override=endpoint_override,
            model_id_override=model_id_override,
        )

    def _flush_session_runtime_to_lifetime(self) -> None:
        stats_state = self._ensure_stats_state()
        if stats_state.start_time <= 0:
            return
        session_sec = stats_state.runtime_sec()
        if self.lifetime_stats.flush_runtime(session_sec):
            stats_state.clear_runtime()

    def stop(self):
        """暂停弹幕：停定时器、mark_stopping AI、清空队列与在途 meta，hide Overlay；不销毁 Config/Web。

        与 quit() 区别：stop 可再次 start()；会话统计写入 session_run_log 并 flush lifetime。
        """
        self._lifetime_flush_timer.stop()
        stats = self._ensure_stats_state()
        self.lifetime_stats.flush_pending()
        self._flush_session_runtime_to_lifetime()
        self.session_run_log.complete(
            ended_at=time.time(),
            input_tokens=stats.total_input_tokens,
            output_tokens=stats.total_output_tokens,
            danmu_count=stats.danmu_count,
        )
        self.screenshot_timer.stop()
        self._live_status_timer.stop()
        self._pending = False
        self.ai_worker.mark_stopping()
        self.ai_in_flight = 0
        self.mic_in_flight = 0
        self._local_fallback_active = False
        self._pending_request_meta.clear()
        self._mic_orchestrator.stop_detector()
        self._is_generating = False
        self._inflight_started_at = 0.0
        self._inflight_screenshot_id = 0
        self._current_batch = None
        self.reply_timer.stop()
        self._pool_topup_timer.stop()
        self.reply_buffer.clear()
        self._get_request_timing_service().reset_started()
        self._latest_requested_screenshot_id = 0
        self._latest_queued_screenshot_id = 0
        self._latest_displayed_screenshot_id = 0
        self._scene_generation = 0
        self._inflight_scene_generation = 0
        self.engine.stop()
        read_svc = self.__dict__.get("_danmu_read_service")
        if read_svc is not None:
            read_svc.on_engine_stopped()
        self._sync_mic_service()
        self.overlay.stop_render_loop()
        self.overlay.hide()
        self.tray.update_state(running=False)
        self.state_changed.emit(False)
        self.logger.info(tr("app.stopped"))

    def toggle(self):
        if self.engine.running:
            self.stop()
        else:
            self.start()

    def quit(self):
        """进程退出：先 stop() 停弹幕，再释放热键/托盘/httpx/历史/配置/WebView/uvicorn。

        顺序 intentional：须先 stop 释放在途 AI，再 close httpx 并 waitForDone 线程池，
        否则 QThreadPool 内仍可能访问已关闭客户端。最后 QApplication.quit()。
        """
        self.logger.info(tr("app.quitting"))

        # 1. 停止弹幕引擎和截图（清零在途与队列，避免线程池仍持有旧 runnable）
        self.stop()
        self._mic_service.stop()
        self._pool_topup_timer.stop()

        read_svc = self.__dict__.get("_danmu_read_service")
        if read_svc is not None:
            read_svc.shutdown()

        # 2. 卸载快捷键（避免进程退出后 keyboard 钩子仍驻留）
        self.hotkey.unregister()

        # 3. 隐藏托盘图标
        self.tray.hide()

        # 4. 先等待在线程池中的请求完成，再关闭 AI HTTP 客户端，避免 worker 访问已关闭 client
        from PyQt6.QtCore import QThreadPool
        pool_done = QThreadPool.globalInstance().waitForDone(2000)
        if not pool_done:
            self.logger.warning("quit timed out waiting for AI worker thread pool")
        self.history_writer.stop()
        self.ai_worker.close()
        self.config.close()

        # 5. 隐藏覆盖层
        self.overlay.hide()

        shell = getattr(self, "webview_shell", None)
        if shell:
            shell.destroy()

        self.stop_web_status_timer()
        server = getattr(self, "web_server", None)
        if server:
            server.stop()

        self.logger.info(tr("app.quit_done"))
        QApplication.quit()

_check_deprecated_launch_args = check_deprecated_launch_args
_web_launch_mode_from_argv = web_launch_mode_from_argv


def main():
    from app.startup_trace import log_startup, mark_app_start
    multiprocessing.freeze_support()
    mark_app_start()
    log_startup("main.begin")
    check_deprecated_launch_args()
    sys.excepthook = global_exception_hook
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    log_startup("qapplication.created")
    from app.single_instance import SingleInstanceGuard
    instance_guard = SingleInstanceGuard()
    if not instance_guard.try_acquire():
        log_startup("single_instance.done", acquired=False)
        return sys.exit(0)
    log_startup("single_instance.done", acquired=True)
    launch_mode = web_launch_mode_from_argv()
    _danmu = DanmuApp(web_launch_mode=launch_mode)
    instance_guard.bind_activate(_danmu.show_settings)
    return sys.exit(app.exec())
if __name__ == "__main__":
    main()
