"""Dedicated Qt thread pools (S-014).

Visual/mic AI use a small isolated pool so hung meme/TTS/probe tasks on the global
pool cannot occupy every worker thread.
"""

from __future__ import annotations

from PyQt6.QtCore import QThreadPool

_ai_pool: QThreadPool | None = None


def ai_worker_pool() -> QThreadPool:
    global _ai_pool
    if _ai_pool is None:
        pool = QThreadPool()
        pool.setMaxThreadCount(2)
        _ai_pool = pool
    return _ai_pool
