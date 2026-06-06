from __future__ import annotations

from pathlib import Path

from tests.boundary_guard_helpers import _baseline_repo, _write, run_boundary_guard


def test_boundary_guard_detects_web_private_access(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/routes.py",
        """
        def register_web_routes(app, bridge, check_token):
            danmu_app = bridge.danmu_app
            return danmu_app._mic_service
        """,
    )

    findings = run_boundary_guard(repo)

    assert any(
        finding.path.replace("\\", "/") == "app/web_api/routes.py"
        and "2.1 / 2.3" in finding.rule
        for finding in findings
    )


def test_boundary_guard_allows_phase2_todo_exception(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_console.py",
        """
        class WebConsoleBridge:
            def __init__(self, danmu_app):
                self.danmu_app = danmu_app

            def refresh_status(self):
                snapshot = self.danmu_app.build_status_snapshot()
                return snapshot

        # TODO(phase2-boundary): reason=temporary lifecycle anchor, current_private_access=danmu_app._web_status_timer, target_public_api=DanmuApp.attach_web_status_timer()
        def attach_web_console(danmu_app):
            danmu_app._web_status_timer = None
            return danmu_app
        """,
    )

    findings = run_boundary_guard(repo)

    assert not any("danmu_app 缁変焦婀佺€涙顔" in finding.message for finding in findings)


def test_boundary_guard_detects_config_conn_spread(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/new_store.py",
        """
        class NewStore:
            def __init__(self, config):
                self.config = config

            def load(self):
                return self.config.conn.execute("select 1")
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("config.conn" in finding.message for finding in findings)


def test_boundary_guard_detects_qtimer_without_pipeline_doc_update(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/new_timer.py",
        """
        from PyQt6.QtCore import QTimer

        timer = QTimer()
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("docs/main-pipeline-sequence.md" in finding.message for finding in findings)


def test_boundary_guard_detects_status_snapshot_builder_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self._web_error_message = ""

            def build_status_snapshot(self):
                return {"running": False, "queue_count": 0}

            def apply_web_config_payload(self, payload):
                return payload
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("StatusSnapshotBuilder" in finding.message for finding in findings)


def test_boundary_guard_detects_web_runtime_state_access_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/routes.py",
        """
        def register_web_routes(app, bridge, check_token):
            danmu_app = bridge.danmu_app
            return danmu_app.web_runtime_state.cached_layout_mode
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("web_runtime_state" in finding.message for finding in findings)


def test_boundary_guard_detects_apply_web_config_payload_bypass(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self._web_error_message = ""

            def build_status_snapshot(self):
                return StatusSnapshotBuilder(self).build()

            def apply_web_config_payload(self, payload):
                self.config.set_batch(payload)
                self.config_changed.emit()
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("apply_web_config_payload" in finding.message for finding in findings)


def test_boundary_guard_detects_custom_model_default_logic_bypass(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/custom_models.py",
        """
        def delete_custom_model(app, index):
            app.config.set_default_model_id("fallback")
            app.config.set("model", "fallback")

        def set_default_custom_model(app, index):
            app.config.set_default_model_id("default")
            app.config.set("model", "default")
            return {"default_model_id": "default"}
        """,
    )

    findings = run_boundary_guard(repo)

    assert any(
        finding.path.replace("\\", "/") == "app/web_api/custom_models.py"
        and "phase2.5" in finding.rule
        for finding in findings
    )
