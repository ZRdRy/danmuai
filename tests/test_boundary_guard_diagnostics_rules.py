from __future__ import annotations

from pathlib import Path

from tests.boundary_guard_helpers import _baseline_repo, _write, run_boundary_guard


def test_boundary_guard_detects_diagnostic_snapshot_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/diagnostic_snapshot.py",
        """
        from app.overlay import DanmuOverlay
        from PyQt6.QtCore import QTimer

        class DiagnosticSnapshotBuilder:
            def __init__(self, app):
                self._app = app

            def build(self):
                app = self._app
                app._rtt_history = []
                app._trigger_api_call()
                return {"timer": QTimer(), "overlay": DanmuOverlay}
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("DiagnosticSnapshot" in finding.message for finding in findings)
    assert any("read-only" in finding.message for finding in findings)
    assert any("QTimer" in finding.message for finding in findings)
    assert any("overlay" in finding.message for finding in findings)


def test_boundary_guard_detects_diagnostics_route_bypass(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/routes.py",
        """
        from app.overlay import DanmuOverlay

        def register_web_routes(app, bridge, check_token):
            @app.get("/api/diagnostics")
            def get_diagnostics():
                danmu_app = bridge.danmu_app
                danmu_app._trigger_api_call()
                return {
                    "ok": True,
                    "diagnostics": danmu_app.build_status_snapshot(),
                    "overlay": DanmuOverlay,
                }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("build_diagnostic_snapshot" in finding.message for finding in findings)
    assert any("/api/status" in finding.message or "build_status_snapshot" in finding.message for finding in findings)
    assert any("overlay" in finding.message for finding in findings)


def test_boundary_guard_detects_status_route_diagnostics_pollution(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_console.py",
        """
        class WebConsoleBridge:
            def __init__(self, danmu_app):
                self.danmu_app = danmu_app

            def refresh_status(self):
                return self.danmu_app.build_status_snapshot()

        def register_status(app, bridge):
            @app.get("/api/status")
            def status():
                return {
                    "running": False,
                    "diagnostics": bridge.danmu_app.build_diagnostic_snapshot(),
                }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("/api/status" in finding.message for finding in findings)


def test_boundary_guard_detects_diagnostics_ui_private_field_reference(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "web/static/app.js",
        """
        function renderDiagnostics() {
            return window._request_started_at_by_id;
        }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("Diagnostics UI" in finding.message for finding in findings)
    assert any("_request_started_at_by_id" in finding.message for finding in findings)


def test_boundary_guard_detects_missing_final_architecture_baseline(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    (repo / "docs" / "final-architecture-baseline.md").unlink()

    findings = run_boundary_guard(repo)

    assert any("final architecture baseline" in finding.message for finding in findings)
