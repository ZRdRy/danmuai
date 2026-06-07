"""Web 控制台 WebSocket 端点：/ws/status 状态推送、/ws/logs 日志推送。

协议：1008 关闭码 → 前端 refreshSession()（token 失效或连接数已满）。
主线程通过 _enqueue_ws 线程安全入队，asyncio 事件循环推送给客户端。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

_WS_BROADCAST_LOG_INTERVAL_SEC = 5.0
_WS_MAX_STATUS_CONSUMERS = 10
_WS_MAX_LOG_CONSUMERS = 10


def _ws_token_valid(query_token: str | None, expected: str) -> bool:
    return bool(query_token and query_token.strip() == expected)


def _enqueue_ws(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    item: Any,
) -> None:
    """主线程 → asyncio 线程安全入队；队列满时丢最旧一条。"""

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


def should_log_broadcast(last_at: float, *, consumer_count: int) -> tuple[bool, float]:
    if consumer_count <= 0:
        return False, last_at
    now = time.monotonic()
    if now - last_at < _WS_BROADCAST_LOG_INTERVAL_SEC:
        return False, last_at
    return True, now


def register_websocket_routes(app, bridge, token: str, websocket_route, websocket_disconnect) -> None:
    async def _ws_status_endpoint(websocket):
        ws_token = websocket.query_params.get("ws_token")
        if not _ws_token_valid(ws_token, token):
            await websocket.close(code=1008, reason="需要登录令牌")
            return
        if len(bridge._ws_status_queues) >= _WS_MAX_STATUS_CONSUMERS:
            await websocket.close(code=1008, reason="连接数已满")
            return
        client = websocket.client
        peer = f"{client.host}:{client.port}" if client else "unknown"
        await websocket.accept()
        bridge._ws_log_debug(f"WebSocket /ws/status accepted peer={peer}")
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        bridge.register_status_consumer(queue)
        cached = bridge._last_status_payload
        if cached:
            await websocket.send_json(cached)
        bridge.status_refresh_requested.emit()
        try:
            while True:
                item = await queue.get()
                await websocket.send_json(item)
        except websocket_disconnect:
            bridge._ws_log_debug(f"WebSocket /ws/status disconnected peer={peer}")
        except Exception as exc:
            bridge._ws_log_debug(
                f"WebSocket /ws/status closed peer={peer} error={exc!r}"
            )
        finally:
            bridge.unregister_status_consumer(queue)

    async def _ws_logs_endpoint(websocket):
        ws_token = websocket.query_params.get("ws_token")
        if not _ws_token_valid(ws_token, token):
            await websocket.close(code=1008, reason="需要登录令牌")
            return
        if len(bridge._ws_log_queues) >= _WS_MAX_LOG_CONSUMERS:
            await websocket.close(code=1008, reason="连接数已满")
            return
        client = websocket.client
        peer = f"{client.host}:{client.port}" if client else "unknown"
        await websocket.accept()
        bridge._ws_log_debug(f"WebSocket /ws/logs accepted peer={peer}")
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        bridge.register_log_consumer(queue)
        try:
            while True:
                item = await queue.get()
                await websocket.send_json(item)
        except websocket_disconnect:
            bridge._ws_log_debug(f"WebSocket /ws/logs disconnected peer={peer}")
        except Exception as exc:
            bridge._ws_log_debug(
                f"WebSocket /ws/logs closed peer={peer} error={exc!r}"
            )
        finally:
            bridge.unregister_log_consumer(queue)

    app.router.routes.insert(0, websocket_route("/ws/status", endpoint=_ws_status_endpoint))
    app.router.routes.insert(0, websocket_route("/ws/logs", endpoint=_ws_logs_endpoint))
