"""
Tests for RecordingController.

Mocks Transport, Audio, and keyboard to isolate orchestration logic.
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from whisper_shell.logic.handshake import HandshakeState, HandshakeStateMachine
from whisper_shell.logic.payload import PayloadBuilder


def _as_mock(value: object) -> MagicMock:
    return cast(MagicMock, value)


# ---------------------------------------------------------------------------
# Helpers — build a controller with fully mocked dependencies
# ---------------------------------------------------------------------------


def _make_controller():
    """
    Constructs a RecordingController with mocked Audio, Transport,
    and keyboard so no hardware or network is touched.
    """
    with (
        patch(
            "whisper_shell.controllers.recording_controller.AudioService"
        ) as MockAudio,
        patch(
            "whisper_shell.controllers.recording_controller.TransportService"
        ) as MockTransport,
        patch("whisper_shell.controllers.recording_controller.keyboard"),
    ):
        # Wire up a real HandshakeStateMachine on the mock transport
        mock_transport = MockTransport.return_value
        mock_transport.handshake = HandshakeStateMachine()
        mock_transport.send_audio = AsyncMock()
        mock_transport.send_json = AsyncMock()
        mock_transport.ensure_connected = AsyncMock(return_value=True)
        mock_transport.disconnect = AsyncMock()
        mock_transport.add_message_listener = MagicMock()

        mock_audio = MockAudio.return_value
        mock_audio.start_capture = MagicMock()
        mock_audio.stop_capture = MagicMock()
        mock_audio.stop_stream = MagicMock()

        loop = asyncio.get_event_loop()
        from whisper_shell.controllers.recording_controller import RecordingController

        ctrl = RecordingController(loop)

        return ctrl


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    def test_initial_state(self):
        ctrl = _make_controller()
        assert ctrl.is_recording is False

    def test_wires_up_handshake_listener(self):
        ctrl = _make_controller()
        # The real HSM should have at least one listener registered
        assert len(ctrl.transport.handshake._listeners) >= 1


# ---------------------------------------------------------------------------
# Toggle recording
# ---------------------------------------------------------------------------


class TestToggleRecording:
    @pytest.mark.asyncio
    async def test_toggle_starts_then_stops(self):
        ctrl = _make_controller()
        assert ctrl.is_recording is False

        await ctrl.toggle_recording()
        assert ctrl.is_recording is True
        _as_mock(ctrl.audio.start_capture).assert_called_once()

        await ctrl.toggle_recording()
        assert ctrl.is_recording is False
        _as_mock(ctrl.audio.stop_capture).assert_called_once()

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        ctrl = _make_controller()
        await ctrl.toggle_recording()  # start
        _as_mock(ctrl.audio.start_capture).assert_called_once()

        ctrl.is_recording = True
        ctrl._start_recording_session()
        # Should still be 1 call — guard prevented double start
        _as_mock(ctrl.audio.start_capture).assert_called_once()

    @pytest.mark.asyncio
    async def test_double_stop_is_noop(self):
        ctrl = _make_controller()
        assert ctrl.is_recording is False
        await ctrl._stop_recording_session()
        _as_mock(ctrl.audio.stop_capture).assert_not_called()


# ---------------------------------------------------------------------------
# Stop sends end-of-stream when authenticated
# ---------------------------------------------------------------------------


class TestStopSession:
    @pytest.mark.asyncio
    async def test_sends_end_of_stream_when_authenticated(self):
        ctrl = _make_controller()
        ctrl.is_recording = True
        ctrl.transport.handshake.transition_to(HandshakeState.AUTHENTICATING)
        ctrl.transport.handshake.transition_to(HandshakeState.AUTHENTICATED)

        await ctrl._stop_recording_session()

        _as_mock(ctrl.transport.send_json).assert_called_once_with(
            PayloadBuilder.build_end_of_stream()
        )

    @pytest.mark.asyncio
    async def test_skips_end_of_stream_when_not_authenticated(self):
        ctrl = _make_controller()
        ctrl.is_recording = True

        await ctrl._stop_recording_session()

        _as_mock(ctrl.transport.send_json).assert_not_called()


# ---------------------------------------------------------------------------
# Audio pipe
# ---------------------------------------------------------------------------


class TestAudioPipe:
    @pytest.mark.asyncio
    async def test_sends_audio_when_authenticated(self):
        ctrl = _make_controller()
        ctrl.is_recording = True
        ctrl.transport.handshake.transition_to(HandshakeState.AUTHENTICATING)
        ctrl.transport.handshake.transition_to(HandshakeState.AUTHENTICATED)

        ctrl.audio_queue.put_nowait(b"\x01\x02")
        ctrl.audio_queue.put_nowait(b"\x03\x04")

        # Stop recording so the pipe exits after draining
        ctrl.is_recording = False
        await ctrl._process_audio_pipe()

        assert _as_mock(ctrl.transport.send_audio).call_count == 2

    @pytest.mark.asyncio
    async def test_buffers_audio_when_not_authenticated(self):
        ctrl = _make_controller()
        ctrl.is_recording = True
        # Handshake still LOCKED — not authenticated

        ctrl.audio_queue.put_nowait(b"\x01\x02")
        ctrl.is_recording = False
        await ctrl._process_audio_pipe()

        _as_mock(ctrl.transport.send_audio).assert_not_called()
        assert ctrl.buffer_manager.count == 1

    @pytest.mark.asyncio
    async def test_flushes_buffer_on_first_authenticated_chunk(self):
        ctrl = _make_controller()
        ctrl.is_recording = True

        # Pre-buffer some audio
        ctrl.buffer_manager.add(b"\xaa\xbb")
        ctrl.buffer_manager.add(b"\xcc\xdd")

        # Now transition to authenticated
        ctrl.transport.handshake.transition_to(HandshakeState.AUTHENTICATING)
        ctrl.transport.handshake.transition_to(HandshakeState.AUTHENTICATED)

        # Queue one more chunk
        ctrl.audio_queue.put_nowait(b"\xee\xff")
        ctrl.is_recording = False
        await ctrl._process_audio_pipe()

        # 2 flushed + 1 live = 3 send_audio calls
        assert _as_mock(ctrl.transport.send_audio).call_count == 3
        assert ctrl.buffer_manager.is_empty


# ---------------------------------------------------------------------------
# Handshake state change callbacks
# ---------------------------------------------------------------------------


class TestHandshakeCallbacks:
    @pytest.mark.asyncio
    async def test_authenticated_logs_debug(self):
        ctrl = _make_controller()
        ctrl._on_handshake_state_changed(HandshakeState.AUTHENTICATED)
        # Should not raise or clear buffer

    @pytest.mark.asyncio
    async def test_failed_clears_buffer(self):
        ctrl = _make_controller()
        ctrl.buffer_manager.add(b"\x01")
        assert not ctrl.buffer_manager.is_empty

        ctrl._on_handshake_state_changed(HandshakeState.FAILED)
        assert ctrl.buffer_manager.is_empty

    @pytest.mark.asyncio
    async def test_banned_clears_buffer(self):
        ctrl = _make_controller()
        ctrl.buffer_manager.add(b"\x01")
        ctrl.transport.handshake.set_error_context("IP_BANNED", "Banned for 60s")

        ctrl._on_handshake_state_changed(HandshakeState.BANNED)
        assert ctrl.buffer_manager.is_empty

    @pytest.mark.asyncio
    async def test_version_outdated_clears_buffer(self):
        ctrl = _make_controller()
        ctrl.buffer_manager.add(b"\x01")
        ctrl.transport.handshake.set_error_context("VERSION_OUTDATED", "Min 3.0.0")

        ctrl._on_handshake_state_changed(HandshakeState.VERSION_OUTDATED)
        assert ctrl.buffer_manager.is_empty

    @pytest.mark.asyncio
    async def test_auth_failed_shows_key_guidance(self):
        ctrl = _make_controller()
        ctrl.transport.handshake.set_error_context("AUTH_FAILED", "Invalid token")
        # Should not raise; just logs guidance
        ctrl._on_handshake_state_changed(HandshakeState.FAILED)

    @pytest.mark.asyncio
    async def test_max_connections_shows_capacity_warning(self):
        ctrl = _make_controller()
        ctrl.transport.handshake.set_error_context(
            "MAX_CONNECTIONS", "10/10 slots full"
        )
        ctrl._on_handshake_state_changed(HandshakeState.FAILED)


# ---------------------------------------------------------------------------
# Server message handling
# ---------------------------------------------------------------------------


class TestServerMessageHandling:
    @pytest.mark.asyncio
    async def test_transcription_triggers_paste(self):
        ctrl = _make_controller()
        with patch.object(ctrl, "_paste_text") as mock_paste:
            await ctrl._handle_server_message(
                {"event": "transcription", "text": "hello world"}
            )
            mock_paste.assert_called_once_with("hello world")

    @pytest.mark.asyncio
    async def test_no_audio_error(self):
        ctrl = _make_controller()
        # Should not raise
        await ctrl._handle_server_message(
            {
                "event": "error",
                "error_code": "NO_AUDIO",
                "message": "No speech",
            }
        )

    @pytest.mark.asyncio
    async def test_transcription_failed_error(self):
        ctrl = _make_controller()
        await ctrl._handle_server_message(
            {
                "event": "error",
                "error_code": "TRANSCRIPTION_FAILED",
                "message": "Engine crash",
            }
        )

    @pytest.mark.asyncio
    async def test_buffer_exceeded_error(self):
        ctrl = _make_controller()
        await ctrl._handle_server_message(
            {
                "event": "error",
                "error_code": "BUFFER_EXCEEDED",
                "message": "Too large",
            }
        )

    @pytest.mark.asyncio
    async def test_server_error(self):
        ctrl = _make_controller()
        await ctrl._handle_server_message(
            {
                "event": "error",
                "error_code": "SERVER_ERROR",
                "message": "Internal",
            }
        )

    @pytest.mark.asyncio
    async def test_unknown_error_code(self):
        ctrl = _make_controller()
        await ctrl._handle_server_message(
            {
                "event": "error",
                "error_code": "",
                "code": 500,
                "message": "???",
            }
        )

    @pytest.mark.asyncio
    async def test_status_event(self):
        ctrl = _make_controller()
        await ctrl._handle_server_message(
            {
                "event": "status",
                "message": "Model loaded",
            }
        )


# ---------------------------------------------------------------------------
# Paste text
# ---------------------------------------------------------------------------


class TestPasteText:
    def test_empty_text_is_noop(self):
        ctrl = _make_controller()
        with patch(
            "whisper_shell.controllers.recording_controller.pyperclip"
        ) as mock_clip:
            ctrl._paste_text("")
            mock_clip.copy.assert_not_called()

    def test_whitespace_only_is_noop(self):
        ctrl = _make_controller()
        with patch(
            "whisper_shell.controllers.recording_controller.pyperclip"
        ) as mock_clip:
            ctrl._paste_text("   ")
            mock_clip.copy.assert_not_called()

    def test_valid_text_copies_to_clipboard(self):
        ctrl = _make_controller()
        with patch(
            "whisper_shell.controllers.recording_controller.pyperclip"
        ) as mock_clip:
            ctrl._paste_text("hello world")
            mock_clip.copy.assert_called_once_with("hello world")


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_disconnects_and_stops_audio(self):
        ctrl = _make_controller()
        await ctrl.shutdown()
        _as_mock(ctrl.transport.disconnect).assert_called_once_with(
            reason="App shutdown"
        )
        _as_mock(ctrl.audio.stop_stream).assert_called_once()
