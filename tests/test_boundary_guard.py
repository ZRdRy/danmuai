from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from scripts.boundary_guard import run_boundary_guard


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _baseline_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    _write(
        repo,
        "main.py",
        """
        from app.application.config_service import apply_web_config_patch
        from app.application.status_snapshot import StatusSnapshotBuilder

        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self._web_error_message = ""

            def build_status_snapshot(self):
                return StatusSnapshotBuilder(self).build()

            def apply_web_config_payload(self, payload):
                apply_web_config_patch(self, payload)
        """,
    )
    _write(
        repo,
        "app/application/status_snapshot.py",
        """
        class StatusSnapshotBuilder:
            def __init__(self, app):
                self.app = app

            def build(self):
                return {"running": False}
        """,
    )
    _write(
        repo,
        "app/application/config_service.py",
        """
        def apply_web_config_patch(app, payload):
            return None

        def set_default_model_selection(config, model_id):
            return model_id
        """,
    )
    _write(
        repo,
        "app/web_console.py",
        """
        from app.application.config_service import apply_web_config_patch

        def apply_config_patch(danmu_app, payload):
            apply_web_config_patch(danmu_app, payload)

        class WebConsoleBridge:
            def __init__(self, danmu_app):
                self.danmu_app = danmu_app

            def refresh_status(self):
                snapshot = self.danmu_app.build_status_snapshot()
                return snapshot
        """,
    )
    _write(
        repo,
        "app/web_api/routes.py",
        """
        def register_web_routes(app, bridge, check_token):
            def _danmu():
                return bridge.danmu_app

            def mic_test():
                return _danmu().run_mic_test(3.0, send_to_ai=False)
        """,
    )
    _write(
        repo,
        "app/web_api/custom_models.py",
        """
        from app.application.config_service import set_default_model_selection

        def delete_custom_model(app, index):
            set_default_model_selection(app.config, "fallback")

        def set_default_custom_model(app, index):
            set_default_model_selection(app.config, "default")
            return {"default_model_id": "default"}
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `web_server`
        - `_web_error_message`
        """,
    )
    _write(
        repo,
        "docs/main-pipeline-sequence.md",
        """
        # Main Pipeline Sequence

        baseline
        """,
    )
    _write(
        repo,
        "docs/phase1-boundary-rules.md",
        """
        # Phase 1 Boundary Rules
        """,
    )
    _write(
        repo,
        "docs/final-architecture-baseline.md",
        """
        # Final Architecture Baseline
        """,
    )

    _git(repo, "init")
    _git(repo, "config", "user.name", "Codex")
    _git(repo, "config", "user.email", "codex@example.com")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


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

    assert not any("danmu_app 绉佹湁瀛楁" in finding.message for finding in findings)


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


def test_boundary_guard_detects_undocumented_runtime_field(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self._web_error_message = ""
                self._new_runtime_flag = 1

            def build_status_snapshot(self):
                return {"running": False}
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("_new_runtime_flag" in finding.message for finding in findings)


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


def test_boundary_guard_detects_legacy_stats_write_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        from app.application.config_service import apply_web_config_patch
        from app.application.status_snapshot import StatusSnapshotBuilder

        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self.stats_state = None

            def build_status_snapshot(self):
                return StatusSnapshotBuilder(self).build()

            def apply_web_config_payload(self, payload):
                apply_web_config_patch(self, payload)

            def bad(self):
                self.danmu_count = 1
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `web_server`
        - `stats_state`
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("StatsState" in finding.message for finding in findings)


def test_boundary_guard_detects_legacy_web_error_write_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        from app.application.config_service import apply_web_config_patch
        from app.application.status_snapshot import StatusSnapshotBuilder

        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self.web_runtime_state = None

            def build_status_snapshot(self):
                return StatusSnapshotBuilder(self).build()

            def apply_web_config_payload(self, payload):
                apply_web_config_patch(self, payload)

            def bad(self):
                self._web_error_message = "boom"
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `web_server`
        - `web_runtime_state`
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("WebRuntimeState" in finding.message for finding in findings)


def test_boundary_guard_detects_legacy_overlay_cache_write_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        from app.application.config_service import apply_web_config_patch
        from app.application.status_snapshot import StatusSnapshotBuilder

        class DanmuApp:
            def __init__(self):
                self.web_server = None
                self.web_runtime_state = None

            def build_status_snapshot(self):
                return StatusSnapshotBuilder(self).build()

            def apply_web_config_payload(self, payload):
                apply_web_config_patch(self, payload)

            def bad(self):
                self._cached_danmu_lines = 20
                self._cached_layout_mode = "fullscreen"
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `web_server`
        - `web_runtime_state`
        - `_cached_danmu_lines`
        - `_cached_layout_mode`
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("_cached_danmu_lines" in finding.message for finding in findings)
    assert any("_cached_layout_mode" in finding.message for finding in findings)


def test_boundary_guard_detects_last_api_trigger_at_write_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        class DanmuApp:
            def __init__(self):
                self._request_scheduler = object()

            def bad(self):
                self._last_api_trigger_at = 1.0
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `_request_scheduler`
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("RequestScheduler" in finding.message for finding in findings)
    assert any("_last_api_trigger_at" in finding.message for finding in findings)


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


def test_boundary_guard_detects_generation_pipeline_writeback_and_forbidden_tokens(
    tmp_path: Path,
) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/generation_pipeline_state.py",
        """
        from PyQt6.QtCore import QTimer

        class GenerationPipelineState:
            @classmethod
            def from_app(cls, app):
                app._latest_displayed_round = 3
                return {
                    "timer": QTimer(),
                    "ai_in_flight": app.ai_in_flight,
                }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("read-only" in finding.message for finding in findings)
    assert any("QTimer" in finding.message for finding in findings)
    assert any("ai_in_flight" in finding.message for finding in findings)


def test_boundary_guard_detects_generation_pipeline_main_pipeline_call(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/generation_pipeline_state.py",
        """
        class GenerationPipelineState:
            @classmethod
            def from_app(cls, app):
                app._trigger_api_call()
                return cls()
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("main pipeline functions" in finding.message for finding in findings)


def test_boundary_guard_detects_runtime_state_projection_bypass(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/runtime_state.py",
        """
        class RuntimeState:
            @classmethod
            def from_app(cls, app):
                return {
                    "latest_displayed_round": getattr(app, "_latest_displayed_round", 0),
                }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("GenerationPipelineState.from_app()" in finding.message for finding in findings)
    assert any("must not bypass GenerationPipelineState" in finding.message for finding in findings)


def test_boundary_guard_detects_request_metadata_state_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/request_metadata_state.py",
        """
        from PyQt6.QtCore import QTimer

        class RequestMetadataState:
            @classmethod
            def from_app(cls, app):
                app._api_schedule_block_reason()
                return {
                    "timer": QTimer(),
                    "last_api_trigger_at": app._last_api_trigger_at,
                    "request_started_at_by_id": app._request_started_at_by_id,
                    "reply_buffer": app.reply_buffer,
                }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("RequestMetadataState" in finding.message for finding in findings)
    assert any("_last_api_trigger_at" in finding.message for finding in findings)
    assert any("_request_started_at_by_id" in finding.message for finding in findings)


def test_boundary_guard_detects_request_metadata_field_in_stats_state(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/stats_state.py",
        """
        class StatsState:
            def __init__(self, app):
                self.last_api_trigger_at = app._last_api_trigger_at
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("StatsState" in finding.message for finding in findings)
    assert any("_last_api_trigger_at" in finding.message for finding in findings)


def test_boundary_guard_detects_request_metadata_field_in_web_runtime_state(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/web_runtime_state.py",
        """
        class WebRuntimeState:
            def __init__(self, app):
                self.request_started_at_by_id = app._request_started_at_by_id
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("WebRuntimeState" in finding.message for finding in findings)
    assert any("_request_started_at_by_id" in finding.message for finding in findings)


def test_boundary_guard_detects_web_api_request_metadata_exposure(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/routes.py",
        """
        def register_web_routes(app, bridge, check_token):
            danmu_app = bridge.danmu_app
            return {
                "last_api_trigger_at": danmu_app._last_api_trigger_at,
            }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("diagnostic snapshot" in finding.message for finding in findings)


def test_boundary_guard_detects_request_started_at_write_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        class DanmuApp:
            def __init__(self):
                self._request_timing_service = object()

            def bad(self):
                self._request_started_at_by_id = {}
                self._request_started_at_by_id.clear()
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `_request_timing_service`
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("RequestTimingService" in finding.message for finding in findings)
    assert any("_request_started_at_by_id" in finding.message for finding in findings)


def test_boundary_guard_detects_web_api_request_started_at_exposure(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/routes.py",
        """
        def register_web_routes(app, bridge, check_token):
            danmu_app = bridge.danmu_app
            return {
                "request_started_at_by_id": danmu_app._request_started_at_by_id,
            }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("_request_started_at_by_id" in finding.message for finding in findings)
    assert any("diagnostic snapshot" in finding.message for finding in findings)


def test_boundary_guard_detects_rtt_history_write_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "main.py",
        """
        class DanmuApp:
            def __init__(self):
                self._request_timing_service = object()

            def bad(self):
                self._rtt_history = []
                self._rtt_history.append(1.0)
        """,
    )
    _write(
        repo,
        "docs/runtime-state-map.md",
        """
        # Runtime State Map

        - `_request_timing_service`
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("RequestTimingService" in finding.message for finding in findings)
    assert any("_rtt_history" in finding.message for finding in findings)


def test_boundary_guard_detects_rtt_history_field_in_stats_state(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/stats_state.py",
        """
        class StatsState:
            def __init__(self, app):
                self.rtt_history = app._rtt_history
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("StatsState" in finding.message for finding in findings)
    assert any("_rtt_history" in finding.message for finding in findings)


def test_boundary_guard_detects_rtt_history_field_in_web_runtime_state(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/web_runtime_state.py",
        """
        class WebRuntimeState:
            def __init__(self, app):
                self.rtt_history = app._rtt_history
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("WebRuntimeState" in finding.message for finding in findings)
    assert any("_rtt_history" in finding.message for finding in findings)


def test_boundary_guard_detects_web_api_rtt_history_exposure(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/web_api/routes.py",
        """
        def register_web_routes(app, bridge, check_token):
            danmu_app = bridge.danmu_app
            return {
                "rtt_history": danmu_app._rtt_history,
            }
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("_rtt_history" in finding.message for finding in findings)
    assert any("diagnostic snapshot" in finding.message for finding in findings)


def test_boundary_guard_detects_request_scheduler_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/request_scheduler.py",
        """
        from app.overlay import DanmuOverlay
        from PyQt6.QtCore import QTimer

        class RequestScheduler:
            def __init__(self, app):
                self.app = app
                self.reply_buffer = app.reply_buffer
                self._scene_generation = app._scene_generation

            def should_fire(self, app):
                app._trigger_api_call()
                app._on_ai_reply()
                app._consume_reply_queue()
                return QTimer()
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("RequestScheduler" in finding.message for finding in findings)
    assert any("reply_buffer" in finding.message for finding in findings)
    assert any("QTimer" in finding.message for finding in findings)
    assert any("God Object" in finding.message for finding in findings)
    assert any("overlay" in finding.message for finding in findings)


def test_boundary_guard_detects_request_timing_service_regression(tmp_path: Path) -> None:
    repo = _baseline_repo(tmp_path)
    _write(
        repo,
        "app/application/request_timing_service.py",
        """
        from app.danmu_engine import DanmuEngine
        from PyQt6.QtCore import QThreadPool

        class RequestTimingService:
            def __init__(self, app):
                self.danmu_app = app
                self.danmu_queue = app.danmu_queue
                self.overlay = app.overlay

            def consume(self, app):
                app._trigger_api_call()
                app._consume_reply_queue()
                return QThreadPool()
        """,
    )

    findings = run_boundary_guard(repo)

    assert any("RequestTimingService" in finding.message for finding in findings)
    assert any("danmu_queue" in finding.message for finding in findings)
    assert any("Overlay" in finding.message for finding in findings)
    assert any("God Object" in finding.message for finding in findings)
    assert any("DanmuEngine" in finding.message for finding in findings)


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
