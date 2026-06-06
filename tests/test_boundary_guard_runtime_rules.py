from __future__ import annotations

from pathlib import Path

from tests.boundary_guard_helpers import _baseline_repo, _write, run_boundary_guard


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
