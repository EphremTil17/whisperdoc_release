"""
Tests for the PayloadBuilder.
"""

from whisper_shell.logic.payload import PayloadBuilder
from whisper_shell.services.config_service import cfg


class TestBuildHello:
    def test_structure(self):
        payload = PayloadBuilder.build_hello(token="key123")
        assert payload["event"] == "hello"
        assert payload["client"] == "whisper.client.terminal"
        assert payload["token"] == "key123"
        assert payload["auth_type"] == "api_key"
        assert payload["incognito"] is False

    def test_version_from_config(self):
        payload = PayloadBuilder.build_hello(token="x")
        assert payload["version"] == cfg.VERSION

    def test_incognito_flag(self):
        payload = PayloadBuilder.build_hello(token="x", incognito=True)
        assert payload["incognito"] is True

    def test_custom_auth_type(self):
        payload = PayloadBuilder.build_hello(token="x", auth_type="oidc")
        assert payload["auth_type"] == "oidc"


class TestBuildEndOfStream:
    def test_structure(self):
        payload = PayloadBuilder.build_end_of_stream()
        assert payload == {"event": "end-of-stream"}
