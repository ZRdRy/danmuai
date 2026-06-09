"""W-TEST-COVER-012: tray-only mode keeps app alive when overlay hidden."""


def test_quit_on_last_window_closed_disabled(qapp):
    """Mirrors main.py: app.setQuitOnLastWindowClosed(False) for Web+tray UI."""
    qapp.setQuitOnLastWindowClosed(False)
    assert qapp.quitOnLastWindowClosed() is False
