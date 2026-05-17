import base64
import io
import json
import sys
import time
import traceback
from datetime import datetime
from json import JSONDecodeError

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from PIL import Image

from app.config_store import ConfigStore
from app.snipper import ScreenCapturer
from app.ai_client import AiWorker
from app.danmu_engine import DanmuEngine, DanmuItem
from app.overlay import DanmuOverlay
from app.tray import TrayManager
from app.hotkey import HotkeyManager
from app.personae import PersonaManager, persona_display_name
from app.templates import TemplateManager
from app.history import DanmuHistory
from app.history_writer import HistoryWriter
from app.logger import SanitizedLogger
from app.reply_queue import AIReplyFIFOBuffer, QueuedReply
from app.reply_parser import normalize_reply_batch, parse_ai_reply_payload
from app.translations import Translator, tr
from ui.settings_panel import SettingsPanel
from ui.log_panel import LogPanel
from ui.template_editor import TemplateEditor
from ui.sidebar_navigation import SidebarNavigation
from ui.control_panel import ControlPanel
from ui.theme import WINDOW_STYLE

IMAGE_MAX_WIDTH = 768
IMAGE_JPEG_QUALITY = 100


def compress_screenshot(pixmap: QPixmap, max_width: int = IMAGE_MAX_WIDTH, quality: int = IMAGE_JPEG_QUALITY) -> str:
    qimage = pixmap.toImage()
    width, height = qimage.width(), qimage.height()
    bits = qimage.bits()
    bits.setsize(height * qimage.bytesPerLine())
    pil_image = Image.frombuffer("RGBA", (width, height), bits, "raw", "BGRA", qimage.bytesPerLine(), 1)
    pil_image = pil_image.convert("RGB")
    if width > max_width:
        ratio = max_width / width
        new_height = int(height * ratio)
        pil_image = pil_image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


class BatchTracker:
    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        self.anchor_item: DanmuItem | None = None
        self.next_generation_time: float = 0.0
        self.next_generation_triggered: bool = False


class MainWindow(QMainWindow):
    def __init__(self, app: "DanmuApp"):
        super().__init__()
        self.danmu_app = app
        self.setWindowTitle(tr("app.window_title"))
        self.resize(1200, 800)
        self.setStyleSheet(WINDOW_STYLE)
        Translator.instance().language_changed.connect(self._retranslate_ui)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 侧边导航
        self.sidebar = SidebarNavigation()
        self.sidebar.page_changed.connect(self._on_page_changed)
        main_layout.addWidget(self.sidebar)
        
        # 内容区域
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("QStackedWidget { background: #f4f7fb; }")
        
        # 创建各个页面
        self.control_panel = ControlPanel()
        self.settings_panel = SettingsPanel(app.config, app)
        self.log_panel = LogPanel(app.logger)
        self.template_panel = TemplateEditor(app.config, app.personae)
        self.content_stack.addWidget(self.control_panel)
        
        # 添加到堆叠窗口
        self.content_stack.addWidget(self.control_panel)
        self.content_stack.addWidget(self.settings_panel)
        self.content_stack.addWidget(self.log_panel)
        self.content_stack.addWidget(self.template_panel)
        
        main_layout.addWidget(self.content_stack)
        
        # 连接控制台信号
        self.control_panel.start_clicked.connect(self._on_start)
        self.control_panel.stop_clicked.connect(self._on_stop)
        
        # 默认显示控制台
        self.content_stack.setCurrentIndex(0)

    def _retranslate_ui(self):
        self.setWindowTitle(tr("app.window_title"))

    def _on_page_changed(self, index: int):
        """页面切换"""
        self.content_stack.setCurrentIndex(index)
        if index == 1:
            self.settings_panel.refresh()
    
    def _on_start(self):
        """开始按钮点击"""
        if self.danmu_app:
            self.danmu_app.start()
    
    def _on_stop(self):
        if self.danmu_app:
            self.danmu_app.stop()
    
    def closeEvent(self, event):
        """主窗口关闭事件：最小化到托盘而非退出程序"""
        event.ignore()
        self.hide()
        # 显示托盘提示
        if self.danmu_app.tray:
            self.danmu_app.tray.show_minimize_hint()


class DanmuApp(QObject):
    state_changed = pyqtSignal(bool)  # running / paused
    config_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config = ConfigStore()
        Translator.set_language(
            Translator.resolve_language(self.config.get("language", ""))
        )
        self.logger = SanitizedLogger()
        self.personae = PersonaManager(self.config)
        self.templates = TemplateManager(self.config)
        self.history = DanmuHistory(self.config)
        self.history_writer = HistoryWriter(self.config)
        self.capturer = ScreenCapturer(self.config)
        self.engine = DanmuEngine(self.config)
        self.overlay = DanmuOverlay(self.config, self.engine)
        self.engine.overlay = self.overlay
        self.tray = TrayManager(self)
        self.hotkey = HotkeyManager(self)
        self.window = MainWindow(self)

        self.ai_worker = AiWorker(self.config)
        self.ai_worker.finished.connect(self._on_ai_reply)
        self.ai_worker.error.connect(self._on_ai_error)

        self.screenshot_round = 0
        self.screenshot_timer = QTimer()
        self.screenshot_timer.timeout.connect(self._capture_screenshot)

        self.ai_in_flight = 0
        self.MAX_IN_FLIGHT = 1
        self.STAGGER_INTERVAL = 1.0
        self._screenshot_scheduled = False

        self._latest_screenshot: QPixmap | None = None
        self._latest_screenshot_time: float = 0.0
        self._is_generating: bool = False
        self._batch_id: int = 0
        self._current_batch: BatchTracker | None = None

        self._rhythm_check_timer = QTimer()
        self._rhythm_check_timer.timeout.connect(self._check_rhythm_trigger)

        self.reply_buffer = AIReplyFIFOBuffer(max_items=8)
        self.danmu_queue = self.reply_buffer
        self.reply_timer = QTimer(self)
        self.reply_timer.setInterval(800)
        self.reply_timer.setSingleShot(True)
        self.reply_timer.timeout.connect(self._consume_reply_queue)

        self._queue_low_watermark = 3
        self._queue_fallback_keep = 3
        self._queue_run_dry_window_ms = 2000
        self._queue_batch_size = 5

        self._pending = False
        self._latest_displayed_round = 0
        self._rtt_history: list[float] = []
        self._request_started_at_by_id: dict[int, float] = {}
        self._last_scene_hash: int = 0
        self._scene_generation: int = 0
        self._latest_screenshot_id: int = 0
        self._latest_requested_screenshot_id: int = 0
        self._latest_queued_screenshot_id: int = 0
        self._latest_displayed_screenshot_id: int = 0

        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._start_time: float = 0.0

        # 连续失败退避机制
        self._consecutive_failures = 0
        self._failure_backoff_paused = False
        self._last_error_message = ""
        self.MAX_CONSECUTIVE_FAILURES = 5

        self.tray.show()
        self.hotkey.register()
        self.config_changed.connect(self._on_config_changed)

        # 统计数据
        self.danmu_count = 0

        startup_notice = self.config.get_startup_notice()
        if startup_notice:
            self.logger.info(startup_notice)

        if not self.config.get_api_key():
            QTimer.singleShot(500, self.show_settings)

        # 首次启动隐私提示
        if self.config.get("privacy_acknowledged", "") != "1":
            self._show_privacy_dialog()

    def _on_config_changed(self):
        self.screenshot_timer.setInterval(1000)
        self.MAX_IN_FLIGHT = 1
        self.STAGGER_INTERVAL = 1.0
        self.reply_buffer.set_max_items(self._queue_capacity())
        self.engine.reload_tracks()
        hotkey_str = self.config.get("hotkey", "Ctrl+Shift+B")
        self.hotkey.set_keys(hotkey_str)

    def _show_privacy_dialog(self):
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self.window)
        msg.setWindowTitle(tr("app.privacy_title"))
        msg.setText(tr("app.privacy_head"))
        msg.setInformativeText(tr("app.privacy_body"))
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        self.config.set("privacy_acknowledged", "1")

    def _set_error_status_safe(self, message: str, is_error: bool):
        window = getattr(self, "window", None)
        control_panel = getattr(window, "control_panel", None)
        if control_panel and hasattr(control_panel, "set_error_status"):
            control_panel.set_error_status(message, is_error=is_error)

    def _schedule_next_screenshot(self, delay_ms: int):
        if self._screenshot_scheduled:
            return
        self._screenshot_scheduled = True
        QTimer.singleShot(delay_ms, self._do_scheduled_screenshot)

    def _do_scheduled_screenshot(self):
        self._screenshot_scheduled = False
        if self.engine.running:
            self._screenshot_loop()

    def _consume_request_timing(self, screenshot_id: int):
        started_at = self._request_started_at_by_id.pop(screenshot_id, None)
        if started_at is None:
            return
        rtt = time.monotonic() - started_at
        self._rtt_history.append(rtt)
        if len(self._rtt_history) > 20:
            self._rtt_history.pop(0)
        self.logger.debug(f"[DEBUG] RTT={rtt:.1f}s, avg={self._rtt_avg():.1f}s, screenshot_id={screenshot_id}")

    def _is_reply_stale(self, screenshot_id: int, captured_at: float, scene_generation: int) -> tuple[bool, str]:
        if scene_generation < self._scene_generation:
            return True, "stale_scene"
        if screenshot_id < getattr(self, "_latest_requested_screenshot_id", 0):
            return True, "superseded_by_newer_request"
        if screenshot_id < self._latest_queued_screenshot_id:
            return True, "superseded_by_newer_reply"
        if self.config.get("drop_stale", "1") == "1":
            max_age = {
                "loose": 12.0,
                "medium": 8.0,
                "strict": 5.0,
            }
            freshness = self.config.get("freshness", "medium")
            if captured_at > 0 and (time.monotonic() - captured_at) > max_age.get(freshness, 8.0):
                return True, "stale_ttl"
        return False, ""

    def _log_reply_drop(self, reason: str, screenshot_id: int, request_round: int, scene_generation: int):
        self.logger.info(
            tr("app.stale_reply_dropped").format(
                reason=reason,
                screenshot_id=screenshot_id,
                request_round=request_round,
                scene_generation=scene_generation,
            )
        )

    def _queue_capacity(self) -> int:
        return self._queue_batch_size + self._queue_fallback_keep

    def _estimated_reply_gap_ms(self) -> int:
        if self.reply_timer.isActive():
            current_interval = self.reply_timer.interval()
            if current_interval > 0:
                return current_interval

        right_count = self._right_visible_count()
        limit = self.engine.max_on_screen()
        right_target = max(1, (limit // 3) if limit > 0 else 2)
        if self._visible_display_count() == 0:
            return 120
        if right_count >= right_target:
            return 1000
        if right_count > 0:
            return 500
        return 200

    def _estimated_inventory_ms(self) -> int:
        inventory_units = self.reply_buffer.size() + self._visible_display_count()
        if inventory_units <= 0:
            return 0
        return inventory_units * self._estimated_reply_gap_ms()

    def _will_queue_run_dry_within(self, threshold_ms: int | None = None) -> bool:
        threshold = self._queue_run_dry_window_ms if threshold_ms is None else threshold_ms
        return self._estimated_inventory_ms() <= threshold

    def _should_request_new_batch(self) -> bool:
        if not self.engine.running:
            return False
        if self._failure_backoff_paused:
            return False
        if self.ai_in_flight >= self.MAX_IN_FLIGHT:
            return False
        if self.reply_buffer.size() <= self._queue_low_watermark:
            return True
        return self._will_queue_run_dry_within()

    def _next_inventory_trigger_delay_ms(self) -> int:
        if self.reply_buffer.is_empty() and self._visible_display_count() == 0:
            return 0
        if self.reply_buffer.size() <= 1:
            return 80
        if self._will_queue_run_dry_within(1000):
            return 120
        return 250

    def _capture_screenshot(self):
        if not self.engine.running:
            return
        pixmap = self.capturer.grab()
        if pixmap is None:
            self.logger.warning(tr("app.capture_failed"))
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

    def _check_rhythm_trigger(self):
        if not self.engine.running:
            return
        if self._is_generating:
            return
        if self._failure_backoff_paused:
            return

        batch = self._current_batch
        if batch is None:
            self._trigger_api_call()
            return

        if batch.next_generation_triggered:
            return

        preload_offset = self._rtt_avg()
        trigger_time = batch.next_generation_time - preload_offset

        if time.monotonic() >= trigger_time:
            batch.next_generation_triggered = True
            self._trigger_api_call()

    def _trigger_api_call(self):
        if self._is_generating:
            self.logger.debug(tr("app.skip_api_generating"))
            return
        if self._latest_screenshot is None:
            self.logger.debug(tr("app.skip_api_no_screenshot"))
            return

        self._is_generating = True
        pixmap = self._latest_screenshot
        self.screenshot_round += 1
        request_round = self.screenshot_round
        screenshot_id = self._latest_screenshot_id
        captured_at = self._latest_screenshot_time
        self._batch_id += 1
        batch_id = self._batch_id
        self._latest_requested_screenshot_id = screenshot_id

        persona = self.personae.pick_random()
        system_pt, user_pt = self.personae.get_prompt(persona)

        screenshot_age = time.monotonic() - captured_at
        self.logger.info(
            tr("app.api_triggered").format(
                batch_id=batch_id,
                screenshot_id=screenshot_id,
                scene_generation=self._scene_generation,
                persona=persona_display_name(persona),
            )
        )

        now = datetime.now().strftime("%H:%M:%S")
        user_pt = user_pt.replace("{current_time}", now)
        user_pt = user_pt.replace("{round}", str(self.screenshot_round))

        self._current_persona = persona
        self._request_started_at_by_id[screenshot_id] = time.monotonic()

        from PyQt6.QtCore import QThreadPool
        from app.runnable import AiRunnable

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
        )
        QThreadPool.globalInstance().start(runnable)

    def _default_batch_interval(self) -> float:
        speed = self.config.get_float("danmu_speed", 2.2)
        fps = 1000.0 / 16.0
        speed_per_second = speed * fps
        if speed_per_second <= 0:
            return 5.0
        distance = self.engine.screen_width * 0.25
        return distance / speed_per_second

    def _screenshot_loop_legacy(self):
        pass

    def _on_ai_reply_legacy(self, text: str, persona_id: str, request_round: int, screenshot_id: int, captured_at: float, scene_generation: int):
        pass

    def _maybe_schedule_screenshot_legacy(self):
        pass

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

    def _can_prefetch_with_buffer(self) -> bool:
        if self.reply_buffer.is_empty():
            return True
        if self.config.get("capture_mode", "continuous") == "smart":
            return False
        limit = self.engine.max_on_screen()
        right_target = max(1, (limit // 3) if limit > 0 else 2)
        if self._visible_display_count() == 0:
            return True
        if self.reply_buffer.size() > self._reply_low_watermark():
            return False
        return self._right_visible_count() < right_target

    def _consume_reply_queue_legacy(self):
        pass

    def _screenshot_loop(self):
        self._capture_screenshot()

    def _on_ai_reply(self, text: str, persona_id: str, request_round: int, screenshot_id: int, captured_at: float, scene_generation: int, input_tokens: int = 0, output_tokens: int = 0):
        self.logger.debug(f"[DEBUG] _on_ai_reply called, text length={len(text)}")
        self.ai_in_flight = max(0, self.ai_in_flight - 1)
        self._is_generating = False

        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        if input_tokens > 0 or output_tokens > 0:
            self.logger.debug(f"[DEBUG] Tokens: input={input_tokens}, output={output_tokens}, total_input={self._total_input_tokens}, total_output={self._total_output_tokens}")

        if self._consecutive_failures > 0:
            self._consecutive_failures = 0
            self._last_error_message = ""
            if self._failure_backoff_paused:
                self._failure_backoff_paused = False
                self._set_error_status_safe("", is_error=False)

        self._consume_request_timing(screenshot_id)

        is_stale, stale_reason = self._is_reply_stale(screenshot_id, captured_at, scene_generation)
        if is_stale:
            self._log_reply_drop(stale_reason, screenshot_id, request_round, scene_generation)
            self._current_batch = None
            return

        normalized_items = normalize_reply_batch(parse_ai_reply_payload(text))
        if not normalized_items:
            return

        batch = BatchTracker(self._batch_id)
        batch.next_generation_time = time.monotonic() + self._default_batch_interval()
        self._current_batch = batch

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
                batch_id=self._batch_id,
            )
            for content_index, item_text in enumerate(normalized_items)
        ]

        self._latest_queued_screenshot_id = screenshot_id
        self.reply_buffer.prepend_batch(
            batch_items,
            preserve_existing=self._queue_fallback_keep,
            preserve_scene_generation=scene_generation,
        )

        self.logger.info(
            tr("app.batch_created").format(
                batch_id=self._batch_id,
                count=len(normalized_items),
                interval=self._default_batch_interval(),
            )
        )

        if not self.reply_timer.isActive():
            self._consume_reply_queue()
        elif self.reply_buffer.size() > self._queue_low_watermark:
            self.reply_timer.stop()
            self._consume_reply_queue()
        else:
            self.reply_timer.setInterval(min(self.reply_timer.interval(), 200))

    def _maybe_schedule_screenshot(self):
        pass

    def _consume_reply_queue(self):
        queued = self.reply_buffer.pop()
        if queued is None:
            return

        is_stale, stale_reason = self._is_reply_stale(
            queued.screenshot_id, queued.captured_at, queued.scene_generation
        )
        if is_stale:
            self._log_reply_drop(stale_reason, queued.screenshot_id, queued.screenshot_round, queued.scene_generation)
            if not self.reply_buffer.is_empty():
                self.reply_timer.start(100)
            return

        self.logger.info(f"[{persona_display_name(queued.persona_id)}] {queued.content}")
        item = self.engine.add_text(queued.content, queued.persona_id, batch_id=queued.batch_id)
        if item:
            self._latest_displayed_round = max(self._latest_displayed_round, queued.screenshot_round)
            self._latest_displayed_screenshot_id = max(self._latest_displayed_screenshot_id, queued.screenshot_id)
            self.history_writer.enqueue(queued.content, queued.persona_id, queued.batch_index)

            batch = self._current_batch
            if batch and batch.anchor_item is None and item.batch_id == batch.batch_id:
                batch.anchor_item = item
                target_x = self.engine.screen_width * 0.75
                distance = item.x - target_x
                if distance > 0 and item.speed > 0:
                    fps = 1000.0 / 16.0
                    speed_per_second = item.speed * fps
                    time_to_boundary = distance / speed_per_second
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
            self.logger.info(tr("app.danmu_not_entered").format(content=f"{queued.content[:20]}..."))

        if not self.reply_buffer.is_empty():
            delay = 100 if item is None else self._estimated_reply_gap_ms()
            self.reply_timer.start(delay)

        self._update_stats()

    def _maybe_adjust_timer(self):
        freq_mode = self.config.get("freq_mode", "auto")
        if freq_mode != "auto":
            return

        limit = self.engine.max_on_screen()
        if limit <= 0:
            return

        current = self._visible_display_count()
        right_count = self._right_visible_count()
        right_target = max(1, limit // 3)
        base_interval = self.config.get_int("screenshot_interval", 3)

        if current == 0:
            accelerated = max(1, base_interval // 2)
            self.screenshot_timer.setInterval(accelerated * 1000)
        elif current >= limit and right_count >= right_target:
            relaxed = base_interval * 2
            self.screenshot_timer.setInterval(relaxed * 1000)
        else:
            self.screenshot_timer.setInterval(base_interval * 1000)

    def _calc_auto_interval(self) -> int:
        limit = self.engine.max_on_screen()
        base = self.config.get_int("screenshot_interval", 3)
        freshness = self.config.get("freshness", "medium")
        freshness_factor = {"loose": 1.5, "medium": 1.0, "strict": 0.6}
        factor = freshness_factor.get(freshness, 1.0)
        if limit > 0:
            per_danmu = max(1, int(base * factor))
            return per_danmu
        return base

    def _rtt_avg(self) -> float:
        if not self._rtt_history:
            return 0.0
        return sum(self._rtt_history) / len(self._rtt_history)

    def _smart_cooldown_ms(self) -> int:
        if len(self._rtt_history) >= 3:
            sorted_rtt = sorted(self._rtt_history)
            idx = int(len(sorted_rtt) * 0.9)
            p90 = sorted_rtt[min(idx, len(sorted_rtt) - 1)]
            return max(1500, min(int(p90 * 0.9 * 1000), 30000))
        base = self.config.get_int("screenshot_interval", 3)
        return max(2000, base * 1000)

    def _on_ai_error(self, msg: str, persona_id: str, request_round: int, screenshot_id: int, captured_at: float, scene_generation: int, input_tokens: int = 0, output_tokens: int = 0):
        self.ai_in_flight = max(0, self.ai_in_flight - 1)
        self._is_generating = False
        self._consume_request_timing(screenshot_id)
        self.logger.error(f"{msg} [persona={persona_id}, round={request_round}, screenshot_id={screenshot_id}, scene_generation={scene_generation}]")

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
            self._screenshot_scheduled = False
            return

        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self.logger.warning(
                tr("app.failure_paused").format(count=self._consecutive_failures, message=msg)
            )
            self._failure_backoff_paused = True
            self._screenshot_scheduled = False
            self._set_error_status_safe(
                tr("app.failure_paused").format(count=self.MAX_CONSECUTIVE_FAILURES, message=msg),
                is_error=True
            )
            return
    
    def _update_stats(self):
        self.danmu_count += 1
        queue_count = self.reply_buffer.size() if hasattr(self.reply_buffer, 'size') else 0
        display_count = self._visible_display_count()
        total_tokens = self._total_input_tokens + self._total_output_tokens
        runtime = time.monotonic() - self._start_time if self._start_time > 0 else 0.0
        self.window.control_panel.update_stats(self.danmu_count, queue_count, display_count, total_tokens, runtime)

    def start(self):
        if not self.config.get_api_key():
            self.logger.warning(tr("app.api_key_missing_warning"))
            self.window.show()
            return
        self.engine.start()
        self.ai_worker.reset_stopping()
        self.ai_in_flight = 0
        self._is_generating = False
        self._batch_id = 0
        self._current_batch = None
        self._latest_screenshot = None
        self._latest_screenshot_time = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._start_time = time.monotonic()
        self._consecutive_failures = 0
        self._failure_backoff_paused = False
        self._last_error_message = ""
        self._request_started_at_by_id = {}
        self._latest_queued_screenshot_id = 0
        self._latest_displayed_screenshot_id = 0
        self._latest_requested_screenshot_id = 0
        self._last_scene_hash = 0
        self._scene_generation = 0
        self.reply_buffer.set_max_items(self._queue_capacity())
        self.screenshot_timer.stop()
        self.screenshot_timer.setInterval(1000)
        self.screenshot_timer.start()
        self._capture_screenshot()
        self._rhythm_check_timer.start(200)
        self.STAGGER_INTERVAL = 1.0
        self.logger.debug(f"[DEBUG] Rhythm mode: screenshot=1s, rhythm_check=200ms")
        if not self.reply_buffer.is_empty() and not self.reply_timer.isActive():
            self.reply_timer.start(200)
        eviction = self.config.get("eviction_mode", "natural")
        if eviction == "accelerate":
            self.engine.trigger_acceleration(60)
        self.overlay.show_for_screen(0)
        self.tray.update_state(running=True)
        self.state_changed.emit(True)
        self._set_error_status_safe("", is_error=False)
        self.logger.info(tr("app.started"))

    def stop(self):
        self.screenshot_timer.stop()
        self._rhythm_check_timer.stop()
        self._pending = False
        self._screenshot_scheduled = False
        self.ai_worker.mark_stopping()
        self.ai_in_flight = 0
        self._is_generating = False
        self._current_batch = None
        self.reply_timer.stop()
        self.reply_buffer.clear()
        self._request_started_at_by_id.clear()
        self._latest_requested_screenshot_id = 0
        self._latest_queued_screenshot_id = 0
        self._latest_displayed_screenshot_id = 0
        self._last_scene_hash = 0
        self._scene_generation = 0
        self.engine.stop()
        self.overlay.hide()
        self.tray.update_state(running=False)
        self.state_changed.emit(False)
        self.logger.info(tr("app.stopped"))

    def toggle(self):
        if self.engine.running:
            self.stop()
        else:
            self.start()

    def show_settings(self):
        self.window.settings_panel.refresh()
        self.window.sidebar.set_active(1)  # 切换到设置页面
        self.window.show()
        self.window.raise_()

    def quit(self):
        """统一退出流程：释放所有资源"""
        self.logger.info(tr("app.quitting"))
        
        # 1. 停止弹幕引擎和截图
        self.stop()
        
        # 2. 卸载快捷键
        self.hotkey.unregister()
        
        # 3. 隐藏托盘图标
        self.tray.hide()
        
        # 4. 关闭数据库连接
        self.ai_worker.close()
        self.ai_worker.close()
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(2000)
        self.history_writer.stop()
        self.config.close()
        
        # 5. 隐藏覆盖层
        self.overlay.hide()
        
        self.logger.info(tr("app.quit_done"))
        QApplication.quit()


def global_exception_hook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        from app.logger import SanitizedLogger
        logger = SanitizedLogger()
        logger.error(tr("app.unhandled_exception_log").format(message=msg))
    except Exception:
        import re
        safe_msg = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "sk-****", msg)
        print(f"FATAL: {safe_msg}", file=sys.stderr)
    if issubclass(exc_type, RuntimeError) and "has been deleted" in str(exc_value):
        return
    try:
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                tr("app.error_title"),
                tr("app.unhandled_exception").format(message=exc_value),
            )
    except Exception:
        pass
    sys.exit(1)


def main():
    sys.excepthook = global_exception_hook
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    danmu = DanmuApp()
    return sys.exit(app.exec())


if __name__ == "__main__":
    main()
