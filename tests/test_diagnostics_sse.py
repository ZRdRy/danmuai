from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.diagnostics_helpers import read_sse_lines


@pytest.mark.skip(reason="Sync TestClient blocks on infinite SSE; covered by DiagnosticsHub unit tests")
def test_diagnostics_sse_endpoint_returns_event_stream():
    """验证 SSE 端点返回正确的 text/event-stream 响应。"""
    import asyncio

    from app.application.diagnostics_hub import DiagnosticsHub
    from app.web_api.routes import register_diagnostics_sse_route

    fastapi_app = FastAPI()
    diagnostics_hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    diagnostics_hub.set_loop(loop)
    danmu_app = type(
        "App",
        (),
        {
            "build_diagnostic_snapshot": staticmethod(
                lambda: {"scheduler": {}, "timing": {}, "runtime_state": {}, "diagnosis": {}}
            )
        },
    )()
    bridge = type("Bridge", (), {"danmu_app": danmu_app})()

    register_diagnostics_sse_route(fastapi_app, diagnostics_hub, bridge, lambda _authorization=None: None)
    client = TestClient(fastapi_app)

    status_code, headers, lines = read_sse_lines(client, max_lines=2)
    assert status_code == 200
    assert headers["content-type"] == "text/event-stream; charset=utf-8"
    assert headers["cache-control"] == "no-cache"
    assert headers["connection"] == "keep-alive"
    assert any(line.startswith("event: hello") for line in lines)

    loop.close()


@pytest.mark.skip(reason="Sync TestClient blocks on infinite SSE; covered by DiagnosticsHub unit tests")
def test_diagnostics_sse_pushes_initial_snapshot():
    """验证 SSE 连接后立即推送初始快照。"""
    import asyncio
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.application.diagnostics_hub import DiagnosticsHub
    from app.web_api.routes import register_diagnostics_sse_route

    fastapi_app = FastAPI()
    diagnostics_hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    diagnostics_hub.set_loop(loop)

    expected_snapshot = {
        "scheduler": {"last_api_trigger_at": 100.0, "block_reason": ""},
        "timing": {"avg_rtt": 0.5, "request_started_count": 0},
        "runtime_state": {"stats": {"danmu_count": 5}},
        "diagnosis": {"scheduler_blocked": False, "high_rtt": False},
    }
    danmu_app = SimpleNamespace(
        build_diagnostic_snapshot=MagicMock(return_value=expected_snapshot)
    )
    bridge = SimpleNamespace(danmu_app=danmu_app)

    register_diagnostics_sse_route(fastapi_app, diagnostics_hub, bridge, lambda _authorization=None: None)
    client = TestClient(fastapi_app)

    _status, _headers, lines = read_sse_lines(client, max_lines=8)

    hello_event = None
    hello_data = None
    snapshot_event = None
    snapshot_data = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("event:"):
            event_name = line[7:].strip()
            if event_name == "hello":
                hello_event = event_name
                if i + 1 < len(lines) and lines[i + 1].startswith("data:"):
                    hello_data = json.loads(lines[i + 1][5:].strip())
                    i += 2
                    continue
            elif event_name == "diagnostic_snapshot":
                snapshot_event = event_name
                if i + 1 < len(lines) and lines[i + 1].startswith("data:"):
                    snapshot_data = json.loads(lines[i + 1][5:].strip())
                    i += 2
                    continue
        i += 1

    assert hello_event == "hello"
    assert hello_data is not None
    assert "event" in hello_data
    assert hello_data["event"] == "hello"
    assert "ts" in hello_data

    assert snapshot_event == "diagnostic_snapshot"
    assert snapshot_data == expected_snapshot

    loop.close()


@pytest.mark.skip(reason="Sync TestClient blocks on infinite SSE; covered by DiagnosticsHub unit tests")
def test_diagnostics_sse_pushes_periodic_updates(monkeypatch):
    """验证 SSE 每 2.5 秒推送更新快照。"""
    import asyncio
    import time
    from types import SimpleNamespace

    from app.application.diagnostics_hub import DiagnosticsHub
    from app.web_api.routes import register_diagnostics_sse_route

    async def _fast_sleep(delay: float) -> None:
        await asyncio.sleep(0.05 if delay >= 2 else 0)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    fastapi_app = FastAPI()
    diagnostics_hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    diagnostics_hub.set_loop(loop)

    call_count = 0

    def make_snapshot():
        nonlocal call_count
        call_count += 1
        return {
            "scheduler": {"call": call_count},
            "timing": {},
            "runtime_state": {},
            "diagnosis": {},
        }

    danmu_app = SimpleNamespace(build_diagnostic_snapshot=make_snapshot)
    bridge = SimpleNamespace(danmu_app=danmu_app)

    register_diagnostics_sse_route(fastapi_app, diagnostics_hub, bridge, lambda _authorization=None: None)
    client = TestClient(fastapi_app)

    start_time = time.monotonic()
    _status, _headers, lines = read_sse_lines(client, max_lines=32, timeout_sec=5.0)
    snapshot_count = sum(1 for line in lines if line.startswith("event: diagnostic_snapshot"))

    elapsed = time.monotonic() - start_time
    assert elapsed < 2.0, f"SSE periodic update took too long: {elapsed:.2f}s"
    assert snapshot_count >= 2

    loop.close()


@pytest.mark.skip(reason="Sync TestClient blocks on infinite SSE; covered by DiagnosticsHub unit tests")
def test_diagnostics_sse_snapshot_contains_correct_fields():
    """验证快照包含 scheduler/timing/runtime_state 字段。"""
    import asyncio
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.application.diagnostics_hub import DiagnosticsHub
    from app.web_api.routes import register_diagnostics_sse_route

    fastapi_app = FastAPI()
    diagnostics_hub = DiagnosticsHub()
    loop = asyncio.new_event_loop()
    diagnostics_hub.set_loop(loop)

    expected_snapshot = {
        "scheduler": {
            "last_api_trigger_at": 100.0,
            "seconds_since_last_trigger": 1.5,
            "min_interval_blocked": False,
            "block_reason": "",
        },
        "timing": {
            "request_started_count": 2,
            "rtt_history_len": 5,
            "avg_rtt": 0.8,
            "smart_cooldown_ms": 3000,
            "recent_rtt_samples": [0.5, 0.6, 0.7, 0.8, 0.9],
        },
        "runtime_state": {
            "web_runtime": {"error_message": "", "is_error": False},
            "stats": {"danmu_count": 10, "total_input_tokens": 100, "total_output_tokens": 200},
            "generation_pipeline": {},
        },
        "diagnosis": {
            "scheduler_blocked": False,
            "high_rtt": False,
            "has_pending_timing": False,
        },
    }
    danmu_app = SimpleNamespace(
        build_diagnostic_snapshot=MagicMock(return_value=expected_snapshot)
    )
    bridge = SimpleNamespace(danmu_app=danmu_app)

    register_diagnostics_sse_route(fastapi_app, diagnostics_hub, bridge, lambda _authorization=None: None)
    client = TestClient(fastapi_app)

    _status, _headers, lines = read_sse_lines(client, max_lines=8)

    snapshot_data = None
    for i, line in enumerate(lines):
        if line == "event: diagnostic_snapshot":
            if i + 1 < len(lines) and lines[i + 1].startswith("data:"):
                snapshot_data = json.loads(lines[i + 1][5:].strip())
                break

    assert snapshot_data is not None
    assert "scheduler" in snapshot_data
    assert "timing" in snapshot_data
    assert "runtime_state" in snapshot_data
    assert "diagnosis" in snapshot_data
    assert "last_api_trigger_at" in snapshot_data["scheduler"]
    assert "block_reason" in snapshot_data["scheduler"]
    assert "avg_rtt" in snapshot_data["timing"]
    assert "request_started_count" in snapshot_data["timing"]
    assert "web_runtime" in snapshot_data["runtime_state"]
    assert "stats" in snapshot_data["runtime_state"]
    assert "generation_pipeline" in snapshot_data["runtime_state"]

    loop.close()
