"""W-TEST-COVER-013: diagnostics SSE route registration smoke test (no live stream)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.application.diagnostics_hub import DiagnosticsHub
from app.web_api.routes import register_diagnostics_sse_route
from fastapi import FastAPI


def test_diagnostics_sse_route_registered_on_app():
    app = FastAPI()
    hub = DiagnosticsHub()
    hub.set_loop(asyncio.new_event_loop())
    bridge = SimpleNamespace(
        danmu_app=SimpleNamespace(
            build_diagnostic_snapshot=MagicMock(
                return_value={"scheduler": {}, "timing": {}, "runtime_state": {}, "diagnosis": {}}
            )
        )
    )
    register_diagnostics_sse_route(app, hub, bridge, lambda _authorization=None: None)
    paths = [getattr(route, "path", "") for route in app.routes]
    assert "/api/diagnostics/events" in paths
    hub._loop.close()
