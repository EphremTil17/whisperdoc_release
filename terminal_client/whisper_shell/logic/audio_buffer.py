import asyncio
from typing import List, Callable, Awaitable
from loguru import logger

class AudioBufferManager:
    """
    Buffers audio chunks during handshake or hot-reload.
    Ensures zero-loss transcription by delaying the stream until authenticated.
    """
    def __init__(self):
        self._buffer: List[bytes] = []
        self._is_buffering = True

    # Safety Cap: 16kHz Mono 16-bit = ~32KB/sec. 
    # 600 seconds (10 mins) = ~19.2MB = ~18,750 chunks (at 1024 frames)
    # We cap at 20,000 chunks for safety.
    MAX_CHUNKS = 20000

    def add(self, chunk: bytes):
        if self._is_buffering:
            if len(self._buffer) >= self.MAX_CHUNKS:
                # Prevent OOM: Pop oldest chunk before adding new one
                self._buffer.pop(0)
                logger.warning("Audio buffer limit reached. Dropping oldest chunk to prevent memory exhaustion.")
            self._buffer.append(chunk)
        else:
            # This shouldn't happen if the controller is logic-correct, 
            # but we keep it for safety.
            pass

    async def flush(self, send_callback: Callable[[bytes], Awaitable[None]]):
        """
        Streams all buffered chunks through the provided callback.
        """
        if not self._buffer:
            self._is_buffering = False
            return

        logger.info(f"Flushing {len(self._buffer)} buffered audio chunks...")
        
        # Create a copy and clear to allow concurrent additions if needed
        # (though usually state transitions block this)
        to_flush = self._buffer.copy()
        self._buffer.clear()
        self._is_buffering = False

        for chunk in to_flush:
            await send_callback(chunk)
        
        logger.debug("Audio buffer flush complete.")

    def clear(self):
        self._buffer.clear()
        self._is_buffering = True

    @property
    def is_empty(self) -> bool:
        return len(self._buffer) == 0

    @property
    def count(self) -> int:
        return len(self._buffer)
