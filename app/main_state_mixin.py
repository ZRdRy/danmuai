"""DanmuApp state and compatibility proxy mixin extracted from main.py."""

from __future__ import annotations

from app.application.request_scheduler import RequestScheduler
from app.application.request_timing_service import RequestTimingService
from app.application.stats_state import StatsState
from app.application.web_runtime_state import WebRuntimeState
from app.personae import normal_reply_count_from_config


class DanmuAppStateMixin:
    def _get_request_scheduler(self) -> RequestScheduler:
        try:
            return object.__getattribute__(self, "_request_scheduler")
        except AttributeError:
            scheduler = RequestScheduler()
            object.__setattr__(self, "_request_scheduler", scheduler)
            return scheduler

    def _get_request_timing_service(self) -> RequestTimingService:
        try:
            return object.__getattribute__(self, "_request_timing_service")
        except AttributeError:
            service = RequestTimingService()
            object.__setattr__(self, "_request_timing_service", service)
            return service

    def _normal_recognition_interval_ms(self) -> int:
        try:
            sec = int(self.config.get("normal_recognition_interval_sec", "5"))
        except (TypeError, ValueError):
            sec = 5
        sec = max(1, min(sec, 60))
        return sec * 1000

    def _normal_reply_count(self) -> int:
        return normal_reply_count_from_config(self.config)

    def _sync_reply_batch_config(self) -> None:
        count = self._normal_reply_count()
        self._reply_scene_count = count
        self._reply_filler_count = 0
        self._queue_batch_size = count
        self._queue_low_watermark = max(1, count // 2)

    def _optional_instance_attr(self, name: str):
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            return None

    def _ensure_stats_state(self) -> StatsState:
        state = self._optional_instance_attr("stats_state")
        if state is None:
            state = StatsState()
            object.__setattr__(self, "stats_state", state)
        return state

    def _ensure_web_runtime_state(self) -> WebRuntimeState:
        state = self._optional_instance_attr("web_runtime_state")
        if state is None:
            state = WebRuntimeState()
            object.__setattr__(self, "web_runtime_state", state)
        return state

    @property
    def danmu_count(self) -> int:
        return self._ensure_stats_state().danmu_count

    @danmu_count.setter
    def danmu_count(self, value: int) -> None:
        self._ensure_stats_state().danmu_count = int(value or 0)

    @property
    def _total_input_tokens(self) -> int:
        return self._ensure_stats_state().total_input_tokens

    @_total_input_tokens.setter
    def _total_input_tokens(self, value: int) -> None:
        self._ensure_stats_state().total_input_tokens = int(value or 0)

    @property
    def _total_output_tokens(self) -> int:
        return self._ensure_stats_state().total_output_tokens

    @_total_output_tokens.setter
    def _total_output_tokens(self, value: int) -> None:
        self._ensure_stats_state().total_output_tokens = int(value or 0)

    @property
    def _start_time(self) -> float:
        return self._ensure_stats_state().start_time

    @_start_time.setter
    def _start_time(self, value: float) -> None:
        self._ensure_stats_state().start_time = float(value or 0.0)

    @property
    def _web_error_message(self) -> str:
        return self._ensure_web_runtime_state().error_message

    @_web_error_message.setter
    def _web_error_message(self, value: str) -> None:
        self._ensure_web_runtime_state().error_message = str(value or "")

    @property
    def _web_error_is_error(self) -> bool:
        return self._ensure_web_runtime_state().is_error

    @_web_error_is_error.setter
    def _web_error_is_error(self, value: bool) -> None:
        self._ensure_web_runtime_state().is_error = bool(value)

    @property
    def _cached_danmu_lines(self) -> int:
        return self._ensure_web_runtime_state().cached_danmu_lines

    @_cached_danmu_lines.setter
    def _cached_danmu_lines(self, value: int) -> None:
        state = self._ensure_web_runtime_state()
        state.cached_danmu_lines = int(value or 0)

    @property
    def _cached_layout_mode(self) -> str:
        return self._ensure_web_runtime_state().cached_layout_mode

    @_cached_layout_mode.setter
    def _cached_layout_mode(self, value: str) -> None:
        state = self._ensure_web_runtime_state()
        state.cached_layout_mode = str(value or "fullscreen")
