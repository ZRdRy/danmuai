import time

from PyQt6.QtCore import QRunnable, pyqtSignal

from app.ai_client import AiWorker
from app.logger import SanitizedLogger
from app.translations import tr


class AiRunnable(QRunnable):
    # Signals emitted from the runnable context
    error_signal = pyqtSignal(str, str, int)

    def __init__(
        self,
        worker: AiWorker,
        pixmap,
        system_pt: str,
        user_pt: str,
        persona_id: str,
        request_round: int,
        screenshot_id: int,
        captured_at: float,
        scene_generation: int,
        compress_fn,
    ):
        super().__init__()
        self.worker = worker
        self.pixmap = pixmap
        self.system_pt = system_pt
        self.user_pt = user_pt
        self.persona_id = persona_id
        self.request_round = request_round
        self.screenshot_id = screenshot_id
        self.captured_at = captured_at
        self.scene_generation = scene_generation
        self.compress_fn = compress_fn
        self.created_at = time.monotonic()

    def run(self):
        started_at = time.monotonic()
        wait_time = started_at - self.created_at
        logger = SanitizedLogger()
        if wait_time > 0.5:
            logger.warning(f"AiRunnable.run() waited {wait_time:.1f}s before starting (thread pool delay)")

        try:
            compress_start = time.monotonic()
            image_data_uri = self.compress_fn(self.pixmap)
            compress_time = time.monotonic() - compress_start
            if compress_time > 0.1:
                logger.warning(f"compress_screenshot took {compress_time:.2f}s")

            request_start = time.monotonic()
            self.worker._request(
                image_data_uri,
                self.system_pt,
                self.user_pt,
                self.persona_id,
                self.request_round,
                self.screenshot_id,
                self.captured_at,
                self.scene_generation,
            )
            request_time = time.monotonic() - request_start
            if request_time > 5.0:
                logger.warning(f"AI request took {request_time:.1f}s")
        except Exception:
            # Ensure the main pipeline can release the in-flight slot.
            self.worker._emit_safe(
                "error",
                tr("runnable.compress_failed"),
                self.persona_id,
                self.request_round,
                self.screenshot_id,
                self.captured_at,
                self.scene_generation,
            )
