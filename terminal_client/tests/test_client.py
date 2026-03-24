"""
Tests for DictationClient initialization.

Verifies that early CLI flags (--version, --clear-key, --health) work
without constructing the full RecordingController.
"""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from whisper_shell.services.config_service import cfg, sec_cfg


class TestHandleEarlyFlags:
    def test_version_flag_exits_zero(self):
        cfg.args.version = True
        try:
            with pytest.raises(SystemExit) as exc:
                from whisper_shell.client import DictationClient

                DictationClient._handle_early_flags()
            assert exc.value.code == 0
        finally:
            cfg.args.version = False

    def test_clear_key_flag_exits_zero(self):
        cfg.args.clear_key = True
        try:
            with pytest.raises(SystemExit) as exc:
                from whisper_shell.client import DictationClient

                DictationClient._handle_early_flags()
            assert exc.value.code == 0
            cast(MagicMock, sec_cfg.clear_key).assert_called()
        finally:
            cfg.args.clear_key = False

    def test_health_flag_success_exits_zero(self):
        cfg.args.health = True
        try:
            with patch(
                "whisper_shell.services.transport_service.TransportService"
            ) as MockTransport:
                MockTransport.return_value.check_health.return_value = True
                # Reload the lazy import target
                with patch.dict(
                    "sys.modules",
                    {
                        "whisper_shell.services.transport_service": MagicMock(
                            TransportService=MockTransport
                        )
                    },
                ):
                    from whisper_shell.client import DictationClient

                    with pytest.raises(SystemExit) as exc:
                        DictationClient._handle_early_flags()
                    assert exc.value.code == 0
        finally:
            cfg.args.health = False

    def test_health_flag_failure_exits_one(self):
        cfg.args.health = True
        try:
            with patch(
                "whisper_shell.services.transport_service.TransportService"
            ) as MockTransport:
                MockTransport.return_value.check_health.return_value = False
                with patch.dict(
                    "sys.modules",
                    {
                        "whisper_shell.services.transport_service": MagicMock(
                            TransportService=MockTransport
                        )
                    },
                ):
                    from whisper_shell.client import DictationClient

                    with pytest.raises(SystemExit) as exc:
                        DictationClient._handle_early_flags()
                    assert exc.value.code == 1
        finally:
            cfg.args.health = False

    def test_no_flags_does_not_exit(self):
        """When no early flags are set, _handle_early_flags returns normally."""
        from whisper_shell.client import DictationClient

        # Should not raise SystemExit
        DictationClient._handle_early_flags()


class TestResolveHostname:
    def test_default_uri(self):
        from whisper_shell.client import _resolve_hostname

        cfg.WS_URI = "ws://localhost:9989/ws"
        assert _resolve_hostname() == "localhost"

    def test_remote_uri(self):
        from whisper_shell.client import _resolve_hostname

        cfg.WS_URI = "wss://api.example.com/ws"
        assert _resolve_hostname() == "api.example.com"

    def test_bare_uri_defaults_to_localhost(self):
        from whisper_shell.client import _resolve_hostname

        cfg.WS_URI = "/ws"
        assert _resolve_hostname() == "localhost"
