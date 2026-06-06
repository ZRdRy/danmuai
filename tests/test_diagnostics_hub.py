from __future__ import annotations


def test_diagnostics_hub_registers_and_unregisters_queue():
    """验证 DiagnosticsHub 的 register/unregister 方法。"""
    import asyncio

    from app.application.diagnostics_hub import DiagnosticsHub

    hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    hub.set_loop(loop)

    assert hub.connection_count == 0

    queue1: asyncio.Queue = asyncio.Queue(maxsize=64)
    hub.register(queue1)
    assert hub.connection_count == 1

    queue2: asyncio.Queue = asyncio.Queue(maxsize=64)
    hub.register(queue2)
    assert hub.connection_count == 2

    hub.unregister(queue1)
    assert hub.connection_count == 1

    hub.unregister(queue1)
    assert hub.connection_count == 1

    hub.unregister(queue2)
    assert hub.connection_count == 0

    loop.close()


def test_diagnostics_hub_broadcast_snapshot_to_queues():
    """验证 DiagnosticsHub 广播快照到已注册队列。"""
    import asyncio
    import time

    from app.application.diagnostics_hub import DiagnosticsHub

    hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    hub.set_loop(loop)

    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    hub.register(queue)

    snapshot = {
        "scheduler": {"block_reason": "test"},
        "timing": {"avg_rtt": 1.0},
        "runtime_state": {},
        "diagnosis": {},
    }
    hub.broadcast_snapshot(snapshot)

    loop.run_until_complete(asyncio.sleep(0.05))

    item = queue.get_nowait()
    assert item["event"] == "diagnostic_snapshot"
    assert item["data"] == snapshot
    assert "ts" in item
    assert abs(item["ts"] - time.time()) < 1.0

    loop.close()


def test_diagnostics_hub_broadcast_without_subscribers():
    """验证无订阅者时广播不崩溃。"""
    from app.application.diagnostics_hub import DiagnosticsHub

    hub = DiagnosticsHub()

    snapshot = {"scheduler": {}, "timing": {}, "runtime_state": {}, "diagnosis": {}}
    hub.broadcast_snapshot(snapshot)
    assert hub.connection_count == 0


def test_diagnostics_hub_queue_full_drops_oldest():
    """验证队列满时丢弃最旧数据。"""
    import asyncio

    from app.application.diagnostics_hub import DiagnosticsHub

    hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    hub.set_loop(loop)

    queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    hub.register(queue)

    for i in range(3):
        snapshot = {"scheduler": {"index": i}, "timing": {}, "runtime_state": {}, "diagnosis": {}}
        hub.broadcast_snapshot(snapshot)
        loop.run_until_complete(asyncio.sleep(0.01))

    assert queue.qsize() == 2

    item1 = queue.get_nowait()
    item2 = queue.get_nowait()
    assert item1["data"]["scheduler"]["index"] == 1
    assert item2["data"]["scheduler"]["index"] == 2

    loop.close()
