"""
Tests for AudioService — only the testable parts (init, capture flags).

The audio callback and stream lifecycle require real hardware
and are not covered here.
"""

import asyncio
from unittest.mock import MagicMock

from whisper_shell.services.audio_service import AudioService


class TestAudioServiceInit:
    def test_initial_state(self):
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        svc = AudioService(loop, queue)
        assert svc.is_recording is False
        assert svc.stream is None
        assert svc.device_rate == 16000
        loop.close()


class TestCaptureFlags:
    def test_start_capture(self):
        loop = asyncio.new_event_loop()
        svc = AudioService(loop, asyncio.Queue())
        svc.start_capture()
        assert svc.is_recording is True
        loop.close()

    def test_stop_capture(self):
        loop = asyncio.new_event_loop()
        svc = AudioService(loop, asyncio.Queue())
        svc.start_capture()
        svc.stop_capture()
        assert svc.is_recording is False
        loop.close()


class TestStopStream:
    def test_stop_stream_when_none(self):
        loop = asyncio.new_event_loop()
        svc = AudioService(loop, asyncio.Queue())
        svc.stop_stream()  # Should not raise
        assert svc.stream is None
        loop.close()

    def test_stop_stream_closes_and_clears(self):
        loop = asyncio.new_event_loop()
        svc = AudioService(loop, asyncio.Queue())
        mock_stream = MagicMock()
        svc.stream = mock_stream
        svc.stop_stream()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert svc.stream is None
        loop.close()
