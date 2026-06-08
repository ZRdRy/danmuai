"""Bounded background queue that flushes entries to SQLite on a fixed interval."""

# W-CONC-001：flush 走 ConfigStore 写入临界区，避免主线程持锁时 database is locked 永久丢失

import logging
import threading
from collections import deque
from datetime import datetime

_logger = logging.getLogger(__name__)


class HistoryWriter:
    def __init__(self, config, flush_interval: float = 2.0):
        self.config = config
        self.flush_interval = flush_interval
        self._buffer: deque[tuple] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HistoryWriter")
        self._thread.start()

    def enqueue(self, content: str, persona: str, round_num: int, image_bytes: bytes | None = None):
        """Buffer one history row. ``content`` must already match on-screen display (truncated)."""
        now = datetime.now().isoformat()
        with self._lock:
            self._buffer.append((now, persona, content, image_bytes, round_num))

    def flush(self):
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
        if not items:
            return
        # W-CONC-001：通过 ConfigStore.with_write_lock() 与主线程 set/set_batch 共享
        # _write_lock，规避主线程持锁时本后台线程 executemany 抛 database is locked
        # 导致整批弹幕历史永久丢失（PRAGMA busy_timeout=5000 不足以覆盖截图/API 延宕）。
        try:
            with self.config.with_write_lock():
                self.config.conn.executemany(
                    "INSERT INTO history (time, persona, content, image, round) VALUES (?,?,?,?,?)",
                    items,
                )
                self.config.conn.commit()
        except Exception:
            _logger.exception("history flush failed items=%d", len(items))

    def _run(self):
        while not self._stop_event.wait(self.flush_interval):
            self.flush()

    def stop(self):
        self._stop_event.set()
        self.flush()
        self._thread.join(timeout=3.0)
