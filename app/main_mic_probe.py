"""Mic probe runnable extracted from main.py."""

from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QCoreApplication, QRunnable, QThread, QThreadPool

from app.ai_client import AiProbeResult, AiWorker

_MIC_PROBE_WAIT_TIMEOUT_SEC = 120.0


class MicProbeRunnable(QRunnable):
    """Mic test-send HTTP in QThreadPool; does not emit AiWorker signals."""

    def __init__(
        self,
        worker: AiWorker,
        image_data_uri: str,
        user_pt: str,
        audio_data_uri: str,
        holder: dict[str, AiProbeResult | None],
        done: threading.Event,
    ) -> None:
        super().__init__()
        self._worker = worker
        self._image_data_uri = image_data_uri
        self._user_pt = user_pt
        self._audio_data_uri = audio_data_uri
        self._holder = holder
        self._done = done
        self.setAutoDelete(True)

    def run(self) -> None:
        from app.translations import tr

        try:
            self._holder["outcome"] = self._worker.run_mic_audio_probe(
                self._image_data_uri,
                self._user_pt,
                self._audio_data_uri,
            )
        except Exception as exc:
            self._holder["outcome"] = AiProbeResult(
                signal="error",
                message=tr("ai.error_request_failed").format(error=exc),
            )
        finally:
            self._done.set()


def run_mic_probe_in_pool(app, image_data_uri: str, user_pt: str, audio_data_uri: str) -> AiProbeResult:
    from app.translations import tr

    holder: dict[str, AiProbeResult | None] = {"outcome": None}
    done = threading.Event()
    QThreadPool.globalInstance().start(
        MicProbeRunnable(
            app.ai_worker,
            image_data_uri,
            user_pt,
            audio_data_uri,
            holder,
            done,
        )
    )
    qt_app = QCoreApplication.instance()
    deadline = time.monotonic() + _MIC_PROBE_WAIT_TIMEOUT_SEC
    if qt_app is not None and QThread.currentThread() is qt_app.thread():
        while not done.is_set() and time.monotonic() < deadline:
            qt_app.processEvents()
            if not done.wait(timeout=0.05):
                continue
            break
    else:
        done.wait(timeout=_MIC_PROBE_WAIT_TIMEOUT_SEC)
    outcome = holder.get("outcome")
    if outcome is None:
        return AiProbeResult(signal="error", message=tr("ai.error_timeout"))
    return outcome
