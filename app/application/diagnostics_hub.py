"""诊断快照 SSE 订阅管理与快照广播。

主线程调用 broadcast_snapshot；uvicorn 线程通过 asyncio.Queue 推送给 SSE 客户端。
无订阅者时立即返回，不阻塞主链路。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


def _enqueue_snapshot(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, item: Any) -> None:
    """跨线程推送快照到 asyncio.Queue。

    Args:
        loop: asyncio 事件循环（uvicorn 线程）
        queue: SSE 连接对应的队列
        item: 要推送的快照数据
    """
    def _put() -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            # 队列满时丢弃最旧的一条，再尝试放入新数据
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

    loop.call_soon_threadsafe(_put)


@dataclass
class DiagnosticsHub:
    """管理 /api/diagnostics/events 连接与诊断快照广播。"""

    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)
    _queues: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置 asyncio 事件循环（由 uvicorn 线程调用）。"""
        self._loop = loop

    @property
    def connection_count(self) -> int:
        """当前 SSE 连接数。"""
        return len(self._queues)

    def register(self, queue: asyncio.Queue) -> None:
        """注册新的 SSE 连接队列。"""
        self._queues.append(queue)

    def unregister(self, queue: asyncio.Queue) -> None:
        """注销 SSE 连接队列。"""
        if queue in self._queues:
            self._queues.remove(queue)

    def broadcast_snapshot(self, snapshot: dict[str, Any]) -> None:
        """向所有 SSE 连接广播诊断快照。

        Args:
            snapshot: 诊断快照数据（由 build_diagnostic_snapshot 生成）
        """
        queues = list(self._queues)
        if not queues:
            return
        loop = self._loop
        if loop is None:
            return

        payload = {
            "event": "diagnostic_snapshot",
            "data": snapshot,
            "ts": time.time(),
        }

        for queue in queues:
            _enqueue_snapshot(loop, queue, payload)
