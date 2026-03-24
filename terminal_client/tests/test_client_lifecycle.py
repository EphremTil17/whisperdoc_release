"""
Tests for DictationClient lifecycle — constructor, start guards, shutdown.
"""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from whisper_shell.services.config_service import sec_cfg


class TestConstructor:
    def test_constructor_acquires_lock_and_creates_loop(self):
        with (
            patch("whisper_shell.client._resolve_hostname", return_value="localhost"),
            patch(
                "whisper_shell.client.acquire_single_instance_lock",
                return_value="fake_lock",
            ),
            patch("whisper_shell.client.RecordingController") as MockCtrl,
            patch("whisper_shell.client.HotkeyService") as MockHotkey,
        ):
            from whisper_shell.client import DictationClient

            client = DictationClient()

            assert client.instance_lock == "fake_lock"
            assert client.loop is not None
            assert client.is_running is True
            MockCtrl.assert_called_once()
            MockHotkey.assert_called_once()

    def test_constructor_exits_when_lock_fails(self):
        with (
            patch(
                "whisper_shell.client.acquire_single_instance_lock", return_value=None
            ),
            pytest.raises(SystemExit) as exc,
        ):
            from whisper_shell.client import DictationClient

            DictationClient()
        assert exc.value.code == 1


class TestStart:
    def test_start_aborts_without_api_key(self):
        with (
            patch(
                "whisper_shell.client.acquire_single_instance_lock", return_value="lock"
            ),
            patch("whisper_shell.client.RecordingController") as MockCtrl,
            patch("whisper_shell.client.HotkeyService"),
        ):
            cast(MagicMock, sec_cfg.get_api_key).return_value = ""
            from whisper_shell.client import DictationClient

            client = DictationClient()
            client.start()
            # Should return early — no hotkey start, no loop.run_forever
            MockCtrl.return_value.audio.start_stream.assert_not_called()
            cast(MagicMock, sec_cfg.get_api_key).return_value = "test-api-key-000"

    def test_start_aborts_on_audio_failure(self):
        with (
            patch(
                "whisper_shell.client.acquire_single_instance_lock", return_value="lock"
            ),
            patch("whisper_shell.client.RecordingController") as MockCtrl,
            patch("whisper_shell.client.HotkeyService") as MockHotkey,
        ):
            MockCtrl.return_value.audio.start_stream.side_effect = Exception(
                "no device"
            )
            cast(MagicMock, sec_cfg.get_api_key).return_value = "test-key"
            from whisper_shell.client import DictationClient

            client = DictationClient()
            client.start()
            MockHotkey.return_value.start.assert_not_called()
            cast(MagicMock, sec_cfg.get_api_key).return_value = "test-api-key-000"


class TestShutdown:
    def test_stop_is_idempotent(self):
        with (
            patch(
                "whisper_shell.client.acquire_single_instance_lock", return_value="lock"
            ),
            patch("whisper_shell.client.RecordingController"),
            patch("whisper_shell.client.HotkeyService") as MockHotkey,
            patch("whisper_shell.client.release_single_instance_lock"),
        ):
            from whisper_shell.client import DictationClient

            client = DictationClient()

            # First stop
            client.is_running = True
            client.loop.stop()  # not running, so shutdown skips loop shutdown
            client.stop()
            assert client.is_running is False

            # Second stop — should be a no-op
            MockHotkey.return_value.stop.reset_mock()
            client.stop()
            MockHotkey.return_value.stop.assert_not_called()

    def test_on_hotkey_bridges_to_async(self):
        with (
            patch(
                "whisper_shell.client.acquire_single_instance_lock", return_value="lock"
            ),
            patch("whisper_shell.client.RecordingController"),
            patch("whisper_shell.client.HotkeyService"),
            patch("asyncio.run_coroutine_threadsafe") as mock_rcts,
        ):
            from whisper_shell.client import DictationClient

            client = DictationClient()
            client._on_hotkey()
            mock_rcts.assert_called_once()
