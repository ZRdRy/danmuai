"""DanmuApp Web/API facade mixin extracted from main.py."""

from __future__ import annotations

from PyQt6.QtCore import QTimer

from app.ai_client import AiProbeResult
from app.api_probe import probe_connection
from app.application.config_service import apply_web_config_patch
from app.application.diagnostic_snapshot import DiagnosticSnapshotBuilder, build_diagnostic_report
from app.application.request_scheduler import RequestScheduler
from app.application.request_timing_service import RequestTimingService
from app.application.status_snapshot import StatusSnapshotBuilder
from app.web_api.custom_models import MASKED_KEY


class DanmuAppWebFacadeMixin:
    def _set_error_status_safe(self, message: str, is_error: bool):
        self._ensure_web_runtime_state().set_error_status(message, is_error=is_error)
        bridge = getattr(self, "web_bridge", None)
        if bridge:
            bridge.publish_status()

    def set_web_error_status(self, message: str, *, is_error: bool) -> None:
        self._set_error_status_safe(message, is_error=is_error)

    def build_status_snapshot(self) -> dict[str, object]:
        return StatusSnapshotBuilder(self).build()

    def build_diagnostic_snapshot(self) -> dict[str, object]:
        return DiagnosticSnapshotBuilder(self).build()

    def build_diagnostic_report(self) -> str:
        return build_diagnostic_report(self.build_diagnostic_snapshot())

    def get_request_scheduler(self) -> RequestScheduler:
        return self._get_request_scheduler()

    def get_request_timing_service(self) -> RequestTimingService:
        return self._get_request_timing_service()

    def api_schedule_block_reason(self, *, enforce_min_interval: bool) -> str:
        return self._api_schedule_block_reason(enforce_min_interval=enforce_min_interval)

    def visible_display_count(self) -> int:
        return self._visible_display_count()

    def build_live_status_snapshot(self):
        return self._build_live_status_snapshot()

    def probe_api_connection(
        self,
        *,
        api_endpoint: str = "",
        api_key: str = "",
        model: str = "",
        api_mode: str = "doubao",
    ) -> dict[str, object]:
        resolved_key = api_key or ""
        if resolved_key == MASKED_KEY:
            resolved_key = self.config.get_api_key()
        result = probe_connection(
            api_endpoint or self.config.get("api_endpoint", ""),
            resolved_key,
            model or self.config.get("model", ""),
            api_mode or self.config.get("api_mode", "doubao"),
        )
        return {
            "ok": result.ok,
            "message": result.message,
            "status_code": result.status_code,
        }

    def apply_web_config_payload(self, payload: dict[str, object]) -> None:
        apply_web_config_patch(self, payload)

    def attach_web_status_timer(self, timer: QTimer) -> QTimer:
        current = getattr(self, "_web_status_timer", None)
        if current is timer:
            return timer
        if current is not None:
            try:
                current.stop()
            except RuntimeError:
                pass
        self._web_status_timer = timer
        return timer

    def detach_web_status_timer(self) -> QTimer | None:
        timer = getattr(self, "_web_status_timer", None)
        self._web_status_timer = None
        return timer

    def stop_web_status_timer(self) -> None:
        timer = getattr(self, "_web_status_timer", None)
        if timer is None:
            return
        try:
            timer.stop()
        except RuntimeError:
            pass

    def set_active_personae(self, active: list[str]) -> None:
        self.personae.set_active(active)
        self.config_changed.emit()

    def get_capture_region_status(self) -> dict[str, object]:
        from app.web_api.capture_region import read_capture_region_status

        state = self._region_selection_state
        if state not in ("selecting", "saved", "cancelled", "invalid"):
            state = "idle"
        return read_capture_region_status(self.config, selection_state=state)

    def request_capture_region_selection(self) -> None:
        from app.region_selector import request_capture_region_selection as _request_selection
        from app.region_selector import screen_for_index
        from app.snipper import resolve_screen_index

        _request_selection(
            self,
            logger=self.logger,
            resolve_screen_index_fn=lambda: resolve_screen_index(self.config),
            screen_for_index_fn=screen_for_index,
            close_region_selector_fn=self._close_region_selector,
            on_finished_fn=self._on_region_selection_finished,
            on_cancelled_fn=self._on_region_selection_cancelled,
            on_destroyed_fn=self._on_region_selector_destroyed,
            publish_status_fn=self._publish_capture_region_status,
        )

    def reset_capture_region(self) -> None:
        from app.web_api.capture_region import clear_capture_region

        self._close_region_selector()
        self._region_selection_state = "idle"
        self._region_selection_screen_index = None
        clear_capture_region(self.config)
        self.config_changed.emit()
        self._publish_capture_region_status()

    def _on_app_focus_changed(self, _old_widget, _new_widget) -> None:
        if self.engine.running and self.overlay.isVisible():
            self.overlay.reassert_topmost_zorder()

    def _close_region_selector(self) -> None:
        from app.region_selector import close_region_selector

        close_region_selector(
            self,
            reassert_topmost_fn=self.overlay.reassert_topmost_zorder,
        )

    def _on_region_selector_destroyed(self, *_args) -> None:
        if self._region_selector is not None:
            self._region_selector = None

    def _on_region_selection_finished(self, rect) -> None:
        from app.region_selector import on_region_selection_finished

        on_region_selection_finished(
            self,
            rect,
            logger=self.logger,
            publish_status_fn=self._publish_capture_region_status,
            config_changed_fn=lambda: self.config_changed.emit(),
        )

    def _on_region_selection_cancelled(self) -> None:
        from app.region_selector import on_region_selection_cancelled

        on_region_selection_cancelled(
            self,
            logger=self.logger,
            publish_status_fn=self._publish_capture_region_status,
        )

    def _publish_capture_region_status(self) -> None:
        bridge = getattr(self, "web_bridge", None)
        if bridge:
            bridge.publish_status()

    def resolve_request_credentials(self):
        return self.ai_worker.resolve_request_credentials()

    def run_mic_audio_probe(self, image_data_uri: str, user_pt: str, audio_data_uri: str):
        return self.ai_worker.run_mic_audio_probe(
            image_data_uri,
            user_pt,
            audio_data_uri,
        )

    def run_mic_probe_in_pool(
        self,
        image_data_uri: str,
        user_pt: str,
        audio_data_uri: str,
    ) -> AiProbeResult:
        from app.main_mic_probe import run_mic_probe_in_pool

        return run_mic_probe_in_pool(self, image_data_uri, user_pt, audio_data_uri)

    def mic_audio_supported(self) -> bool:
        return self._mic_audio_supported()

    def capture_mic_test_sample(self, duration_sec: float, *, keep_running: bool):
        from app.mic_test import capture_mic_sample

        return capture_mic_sample(
            self._mic_service,
            duration_sec,
            keep_running=keep_running,
        )

    def send_mic_test_probe(self, image_data_uri: str, user_pt: str, audio_data_uri: str):
        from app.mic_test_send import send_mic_probe

        return send_mic_probe(
            self,
            image_data_uri,
            user_pt,
            audio_data_uri,
        )

    def run_mic_test(self, duration_sec: float, *, send_to_ai: bool = False) -> dict[str, object]:
        from dataclasses import asdict

        from app.mic_service import mic_mode_enabled

        if send_to_ai:
            from app.mic_test_send import run_mic_test_send

            resolved = self.ai_worker.resolve_mic_request_credentials()
            active_model = resolved[2] if resolved else ""
            result = run_mic_test_send(self, duration_sec)
            self.logger.info(
                "mic test send "
                f"model={active_model or 'unknown'} "
                f"ok={result.ok} level={result.level} pcm_bytes={result.pcm_bytes} "
                f"rms={result.rms} audio_attached={result.audio_attached} "
                f"input_tokens={result.input_tokens} output_tokens={result.output_tokens} "
                f"error={result.error or 'none'}"
            )
            return asdict(result)

        from app.mic_test import run_mic_test

        keep_running = mic_mode_enabled(self.config)
        result = run_mic_test(
            self._mic_service,
            duration_sec,
            keep_running=keep_running,
        )
        self.logger.info(
            "mic test "
            f"ok={result.ok} level={result.level} pcm_bytes={result.pcm_bytes} "
            f"rms={result.rms} peak={result.peak} wav_ok={result.wav_ok} "
            f"device={result.default_input or 'unknown'}"
        )
        return asdict(result)
