"""OBS / 直播伴侣网页弹幕层：SSE 订阅管理与批次广播。

主线程（DanmuApp）调用 broadcast_batch；uvicorn 线程通过 asyncio.Queue 推送给 SSE 客户端。
无订阅者时立即返回，不阻塞主链路。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


def _enqueue_overlay(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, item: Any) -> None:
    def _put() -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
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
class LiveOverlayHub:
    """管理 /api/live-overlay/events 连接与弹幕批次广播。"""

    _loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)
    _queues: list[asyncio.Queue] = field(default_factory=list, repr=False)
    _recent: deque = field(default_factory=lambda: deque(maxlen=80), repr=False)
    last_broadcast_at: float | None = field(default=None, repr=False)
    last_batch_size: int = field(default=0, repr=False)
    last_source: str = field(default="", repr=False)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def connection_count(self) -> int:
        return len(self._queues)

    def register(self, queue: asyncio.Queue) -> None:
        self._queues.append(queue)

    def unregister(self, queue: asyncio.Queue) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    def recent_items(self) -> list[dict[str, Any]]:
        return list(self._recent)

    def _remember(self, payload: dict[str, Any]) -> None:
        if payload.get("event") == "danmu_item":
            self._recent.append(payload)

    def snapshot(self) -> dict[str, Any]:
        return {
            "connections": self.connection_count,
            "last_broadcast_at": self.last_broadcast_at,
            "last_batch_size": self.last_batch_size,
            "last_source": self.last_source or None,
        }

    def _build_batch_payload(
        self,
        items: list[str],
        *,
        source: str,
        batch_id: str | int | None,
    ) -> dict[str, Any]:
        return {
            "event": "danmu_batch",
            "items": list(items),
            "source": source,
            "ts": time.time(),
            "batch_id": batch_id,
        }

    def _build_item_payload(
        self,
        text: str,
        *,
        y: float,
        screen_width: float,
        screen_height: float,
        speed: float,
        source: str,
    ) -> dict[str, Any]:
        return {
            "event": "danmu_item",
            "text": text,
            "y": y,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "speed": speed,
            "source": source,
            "ts": time.time(),
        }

    def _publish(self, payload: dict[str, Any], *, source: str, batch_size: int = 1) -> None:
        queues = list(self._queues)
        if not queues:
            return
        loop = self._loop
        if loop is None:
            return
        self.last_broadcast_at = float(payload["ts"])
        self.last_batch_size = batch_size
        self.last_source = source
        for queue in queues:
            _enqueue_overlay(loop, queue, payload)

    def broadcast_item(
        self,
        text: str,
        *,
        y: float,
        screen_width: float,
        screen_height: float,
        speed: float,
        source: str = "ai",
    ) -> None:
        """单条上屏同步（与 Qt Overlay 同一时刻、同一轨道 Y）。"""
        if not text:
            return
        payload = self._build_item_payload(
            text,
            y=y,
            screen_width=screen_width,
            screen_height=screen_height,
            speed=speed,
            source=source,
        )
        self._remember(payload)
        self._publish(payload, source=source, batch_size=1)

    def broadcast_batch(
        self,
        items: list[str],
        *,
        source: str,
        batch_id: str | int | None = None,
    ) -> None:
        if not items:
            return
        line_height = 40.0
        top_margin = 50.0
        screen_w = 1920.0
        screen_h = 1080.0
        speed = 2.0
        for index, line in enumerate(items):
            if not line:
                continue
            self.broadcast_item(
                line,
                y=top_margin + index * line_height,
                screen_width=screen_w,
                screen_height=screen_h,
                speed=speed,
                source=source,
            )

    def broadcast_test(self, items: list[str] | None = None) -> None:
        default = ["DanmuAI 测试弹幕", "直播输出连接正常"]
        self.broadcast_batch(items or default, source="test", batch_id=None)
