
import pytest
from app.bundle_paths import is_frozen, project_root, resource_path

from tests.conftest import _ensure_feedback_static_images


def test_project_root_is_repo_in_dev():
    assert not is_frozen()
    root = project_root()
    assert (root / "main.py").is_file()
    assert (root / "web" / "static" / "index.html").is_file()


def test_resource_path_data_pool():
    pool = resource_path("data", "danmu_pool_zh.json")
    assert pool.is_file()
    assert pool.parent == project_root() / "data"


def test_feedback_static_images_packaged():
    root = project_root()
    _ensure_feedback_static_images()
    for name in (
        "qrcode_1779738450536.jpg",
        "mm_reward_qrcode_1779738306814.png",
    ):
        path = root / "web" / "static" / "image" / name
        src = root / "image" / name
        if not path.is_file() and not src.is_file():
            pytest.skip(f"feedback assets missing: {src}")
        assert path.is_file(), f"missing {path}; run python scripts/copy_feedback_images.py"
        assert path.stat().st_size > 0


def test_feedback_page_in_index_html():
    html = (project_root() / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-page="feedback"' in html
    assert 'id="page-feedback"' in html
    assert 'id="feedbackForm"' in html
    assert 'id="feedbackContent"' in html
    assert "/static/image/qrcode_1779738450536.jpg" in html
    assert 'id="rewardModal"' in html


def test_announcements_page_in_index_html():
    html = (project_root() / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-page="announcements"' in html
    assert 'id="page-announcements"' in html
    assert 'id="announcementsList"' in html
    assert 'id="announcementsNavBadge"' in html
    assert 'id="overviewAnnouncementBanner"' in html
    assert 'id="btnOverviewAnnouncementDismiss"' in html
    assert "/static/supabase-client.js" in html


def test_overview_announcement_banner_in_content_pages_js():
    root = project_root()
    app_js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
    content_js = (root / "web" / "static" / "modules" / "content-pages.js").read_text(
        encoding="utf-8"
    )
    assert "danmu_announcements_overview_banner_dismissed_id" in content_js
    assert "function buildAnnouncementSnippet" in content_js
    assert "function updateOverviewAnnouncementBanner" in content_js
    assert "function buildAnnouncementSnippet" not in app_js


def test_error_report_modal_in_index_html():
    html = (project_root() / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="errorReportModal"' in html
    assert 'id="btnErrorReportSubmit"' in html
    assert 'id="btnErrorReportDismiss"' in html


def test_app_js_imports_transport_module():
    root = project_root()
    app_js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "from './modules/transport.js'" in app_js
    assert "apiFetch" in app_js
    assert "startRealtimeTransport" in app_js
    transport_js = (root / "web" / "static" / "modules" / "transport.js").read_text(
        encoding="utf-8"
    )
    assert "export async function apiFetch" in transport_js
    assert "export function startRealtimeTransport" in transport_js


def test_web_console_modules_exist():
    root = project_root()
    modules = root / "web" / "static" / "modules"
    for name in (
        "transport.js",
        "status.js",
        "logs.js",
        "diagnostics.js",
        "settings.js",
        "content-pages.js",
    ):
        path = modules / name
        assert path.is_file(), f"missing {path}"
        assert path.stat().st_size > 0
    html = (root / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' in html
    assert "/static/app.js" in html


def test_status_js_renders_legacy_lifetime_token_note():
    root = project_root()
    status_js = (root / "web" / "static" / "modules" / "status.js").read_text(encoding="utf-8")
    assert "statLifetimeTokenNote" in status_js
    assert "const legacyExtra = lifetimeTotal - lifetimeIn - lifetimeOut;" in status_js
    assert "另有升级前累计" in status_js
    assert "formatTokenCount(legacyExtra)" in status_js


def test_error_report_flow_in_app_js():
    root = project_root()
    js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
    status_js = (root / "web" / "static" / "modules" / "status.js").read_text(encoding="utf-8")
    assert "function maybePromptErrorReport" in js
    assert "function collectErrorReportContext" in js
    assert "function extractErrorReportSearchTerms" in js
    assert "function findErrorLogAnchorIndex" in js
    assert "localStorage.setItem(ERROR_REPORT_DISMISS_STORAGE" in js
    assert "submitErrorReport" in js
    assert "statusHadError" in status_js


def test_api_settings_visible_in_simplified_mode():
    """记忆与温度控件不得带 settings-full-only，否则简化模式下会被 CSS 隐藏。"""
    html = (project_root() / "web" / "static" / "index.html").read_text(encoding="utf-8")
    for field_id in ("memory_mode", "memory_window", "temperature"):
        idx = html.index(f'id="{field_id}"')
        chunk = html[max(0, idx - 120) : idx]
        assert "settings-full-only" not in chunk, field_id
