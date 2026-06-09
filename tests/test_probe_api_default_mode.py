"""Probe API connection default api_mode alignment."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.main_web_facade_mixin import DanmuAppWebFacadeMixin


class _ProbeHost(DanmuAppWebFacadeMixin):
    def __init__(self, config):
        self.config = config


def test_probe_api_connection_uses_config_default_openai_mode():
    host = _ProbeHost(SimpleNamespace(
        get_api_key=MagicMock(return_value="sk-test"),
        get=MagicMock(side_effect=lambda k, d="": {"api_endpoint": "https://api.example.com/v1", "api_mode": "openai", "model": "gpt-4o"}.get(k, d)),
    ))
    with patch("app.main_web_facade_mixin.probe_connection") as mock_probe:
        mock_probe.return_value = MagicMock(ok=True, message="ok", status_code=200)
        host.probe_api_connection()
    mock_probe.assert_called_once_with(
        "https://api.example.com/v1",
        "",
        "gpt-4o",
        "openai",
    )
