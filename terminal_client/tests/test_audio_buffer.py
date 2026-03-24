"""
Tests for AudioBufferManager.
"""

from unittest.mock import AsyncMock

import pytest
from whisper_shell.logic.audio_buffer import AudioBufferManager


class TestAudioBuffer:
    def test_starts_empty(self):
        buf = AudioBufferManager()
        assert buf.is_empty
        assert buf.count == 0

    def test_add_and_count(self):
        buf = AudioBufferManager()
        buf.add(b"\x01\x02")
        buf.add(b"\x03\x04")
        assert buf.count == 2
        assert not buf.is_empty

    def test_clear(self):
        buf = AudioBufferManager()
        buf.add(b"\x01")
        buf.clear()
        assert buf.is_empty

    @pytest.mark.asyncio
    async def test_flush_sends_all_chunks(self):
        buf = AudioBufferManager()
        buf.add(b"\x01")
        buf.add(b"\x02")
        buf.add(b"\x03")
        callback = AsyncMock()
        await buf.flush(callback)
        assert callback.call_count == 3
        assert buf.is_empty

    @pytest.mark.asyncio
    async def test_flush_empty_buffer(self):
        buf = AudioBufferManager()
        callback = AsyncMock()
        await buf.flush(callback)
        callback.assert_not_called()

    def test_max_chunks_drops_oldest(self):
        buf = AudioBufferManager()
        for i in range(AudioBufferManager.MAX_CHUNKS + 5):
            buf.add(bytes([i % 256]))
        assert buf.count == AudioBufferManager.MAX_CHUNKS
