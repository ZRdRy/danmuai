import threading
import time
from unittest.mock import MagicMock

from app.config_store import ConfigStore
from app.history_writer import HistoryWriter


def test_history_writer_logs_flush_failures(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr("app.history_writer._logger", logger)

    config = MagicMock()
    config.conn.executemany.side_effect = RuntimeError("db locked")

    writer = HistoryWriter(config, flush_interval=60.0)
    writer.enqueue("hello", "persona", 1)
    writer.flush()
    writer.stop()

    logger.exception.assert_called_once()


def test_history_writer_waits_for_config_store_write_lock(tmp_path):
    """W-CONC-001：主线程持 _write_lock 时，后台线程 flush() 必须等待锁释放，
    而**不**抛 OperationalError('database is locked') 丢整批弹幕历史。
    """
    store = ConfigStore(db_path=tmp_path / "config.db")
    writer = HistoryWriter(store, flush_interval=60.0)
    try:
        writer.enqueue("hello-1", "persona-A", 1)
        writer.enqueue("hello-2", "persona-B", 2)

        # 主线程模拟「持锁做 set」：直接 _write_lock.acquire，避免触发 _cache 副作用
        assert store._write_lock.acquire(timeout=2.0) is True
        flush_result: dict = {}

        def _bg_flush():
            try:
                writer.flush()
                flush_result["ok"] = True
                flush_result["error"] = None
            except Exception as e:  # pragma: no cover - 仅在退步时报
                flush_result["ok"] = False
                flush_result["error"] = repr(e)

        t = threading.Thread(target=_bg_flush, name="test-flush-bg")
        t.start()
        # 让后台线程先尝试拿锁并阻塞
        time.sleep(0.2)
        assert t.is_alive(), "flush 应该在主线程持锁时阻塞等待，而不是直接抛 OperationalError"
        # 释放锁；后台线程应在 2s 内完成写入
        store._write_lock.release()
        t.join(timeout=2.0)
        assert not t.is_alive(), "释放锁后 flush 仍应完成"
        assert flush_result.get("ok") is True, f"flush 异常：{flush_result.get('error')}"

        # 验证 items 已落到 history 表
        rows = store.conn.execute(
            "SELECT time, persona, content, round FROM history ORDER BY id ASC"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1:] == ("persona-A", "hello-1", 1)
        assert rows[1][1:] == ("persona-B", "hello-2", 2)
    finally:
        writer.stop()
        store.close()


def test_history_writer_does_not_call_executemany_without_lock():
    """W-CONC-001：flush() 必须走 ``config.with_write_lock()`` 上下文；不能用
    monkeypatch 旁路掉写入临界区（防止后续维护者悄悄退步为裸 executemany）。
    """
    ctx_entered = threading.Event()
    captured_executemany_calls: list = []

    class _StubConn:
        def executemany(self, sql, params):
            # 仅当 ctx 已 enter 时才记录，防止退步到 with 块外调用
            assert ctx_entered.is_set(), "executemany 必须在 with_write_lock 临界区内调用"
            captured_executemany_calls.append((sql, params))
            return None

        def commit(self):
            assert ctx_entered.is_set(), "commit 必须在 with_write_lock 临界区内调用"
            return None

    class _FakeContextManager:
        def __enter__(self):
            ctx_entered.set()
            return stub_conn

        def __exit__(self, exc_type, exc, tb):
            return False

    stub_conn = _StubConn()

    class _StubConfig:
        pass

    config = _StubConfig()
    config.conn = stub_conn

    def _with_write_lock():
        return _FakeContextManager()

    config.with_write_lock = _with_write_lock

    writer = HistoryWriter(config, flush_interval=60.0)
    try:
        writer.enqueue("only-once", "persona-X", 1)
        writer.flush()
        # 验证：flush 走 with_write_lock 临界区，且仅调用一次 executemany
        assert ctx_entered.is_set(), "flush 应进入 with_write_lock 上下文"
        assert len(captured_executemany_calls) == 1
        sql, params = captured_executemany_calls[0]
        assert "INSERT INTO history" in sql
        assert len(params) == 1
        # (time, persona, content, image, round)
        assert params[0][1:] == ("persona-X", "only-once", None, 1)
    finally:
        writer.stop()
