import asyncio

import pyperclip
from colorama import Fore, Style
from loguru import logger
from pynput import keyboard

from ..logic.audio_buffer import AudioBufferManager
from ..logic.handshake import HandshakeState
from ..logic.messages import ServerMessage
from ..logic.payload import PayloadBuilder
from ..services.audio_service import AudioService
from ..services.config_service import cfg
from ..services.transport_service import TransportService


class RecordingController:
    """
    Orchestrates the recording lifecycle.
    Bridges Transport, Audio, and UI logic (paste).
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Services
        self.audio = AudioService(loop, self.audio_queue)
        self.transport = TransportService()

        # Logic
        self.buffer_manager = AudioBufferManager()
        self.kb = keyboard.Controller()

        # State
        self.is_recording = False
        self._background_tasks: set[asyncio.Task[object]] = set()

        # Wire up transport listeners
        self.transport.add_message_listener(self._handle_server_message)
        self.transport.handshake.add_listener(self._on_handshake_state_changed)

    def _track_task(self, task: asyncio.Task[object]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def toggle_recording(self):
        """Main entry point triggered by Hotkey."""
        if not self.is_recording:
            self._start_recording_session()
        else:
            await self._stop_recording_session()

    def _start_recording_session(self):
        if self.is_recording:
            return

        self.is_recording = True
        logger.info(f"{Fore.CYAN}Recording...{Style.RESET_ALL}")

        # 1. Start Hardware Capture Instantly (Zero-Latency)
        self.audio.start_capture()

        # 2. Reset Buffer for new session
        self.buffer_manager.clear()

        # 3. Ensure Transport is connected in background (Auto-Wake)
        self._track_task(asyncio.create_task(self.transport.ensure_connected()))

        # 4. Start the Pipe loop
        self._track_task(asyncio.create_task(self._process_audio_pipe()))

    async def _stop_recording_session(self):
        if not self.is_recording:
            return

        self.is_recording = False
        self.audio.stop_capture()
        logger.info(f"{Fore.CYAN}Stopped. Processing...{Style.RESET_ALL}")

        if self.transport.handshake.state == HandshakeState.AUTHENTICATED:
            await self.transport.send_json(PayloadBuilder.build_end_of_stream())

    async def _process_audio_pipe(self):
        """
        Continuously pulls data from audio queue and directs it to
        the Buffer or the Socket depending on handshake state.
        """
        while self.is_recording or not self.audio_queue.empty():
            try:
                chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.1)

                if self.transport.handshake.state == HandshakeState.AUTHENTICATED:
                    if not self.buffer_manager.is_empty:
                        await self.buffer_manager.flush(self.transport.send_audio)
                    await self.transport.send_audio(chunk)
                else:
                    self.buffer_manager.add(chunk)

            except asyncio.TimeoutError:
                if not self.is_recording:
                    break
            except Exception as e:
                logger.error(f"Audio pipe error: {e}")
                break

    def _on_handshake_state_changed(self, state: HandshakeState):
        """Reacts to handshake state transitions."""
        if state == HandshakeState.AUTHENTICATED:
            logger.debug("Handshake Authenticated. Pipe loop will flush buffer.")
        elif state == HandshakeState.FAILED:
            error_code = self.transport.handshake.last_error_code
            message = self.transport.handshake.last_message or "Unknown error"
            if error_code == "AUTH_FAILED":
                logger.error(
                    f"Authentication failed: {message}. Run --clear-key to re-enter your API key."
                )
            elif error_code == "MAX_CONNECTIONS":
                logger.warning(f"Server at capacity: {message}. Try again shortly.")
            else:
                logger.error(f"Handshake failed: {message}")
            self.buffer_manager.clear()
        elif state == HandshakeState.BANNED:
            message = self.transport.handshake.last_message or "IP banned"
            logger.error(f"{Fore.RED}Banned: {message}{Style.RESET_ALL}")
            self.buffer_manager.clear()
        elif state == HandshakeState.VERSION_OUTDATED:
            message = self.transport.handshake.last_message or "Client version outdated"
            logger.error(
                f"{Fore.RED}{message}. Please update your client.{Style.RESET_ALL}"
            )
            self.buffer_manager.clear()

    async def _handle_server_message(self, msg: ServerMessage) -> None:
        """Processes transcription results and server errors.

        Intentionally async despite no current awaits. TransportService dispatches
        all MessageListener callbacks with `await cb(msg)`, so this must return a
        coroutine. Future work that would naturally use this — writing results to an
        async queue, aiofiles logging, or rate-limited paste — should be added here
        directly rather than spawning a new task.
        """
        event = msg.get("event")

        if "text" in msg:
            self._paste_text(msg["text"])
        elif event == "error":
            error_code = msg.get("error_code", "")
            message = msg.get("message", "Unknown error")
            if error_code == "NO_AUDIO":
                logger.info(f"No audio detected: {message}")
            elif error_code == "TRANSCRIPTION_FAILED":
                logger.error(f"Transcription failed: {message}")
            elif error_code == "BUFFER_EXCEEDED":
                logger.warning(f"Audio buffer exceeded: {message}")
            elif error_code == "SERVER_ERROR":
                logger.error(f"Server error: {message}")
            else:
                logger.error(
                    f"Server Error ({error_code or msg.get('code')}): {message}"
                )
        elif event == "status":
            logger.info(f"Server Status: {msg.get('message')}")

    def _paste_text(self, text: str) -> None:
        if not text or not text.strip():
            return

        from ..logic.sanitizer import Sanitizer

        safe_text = Sanitizer.sanitize(text)
        if not safe_text:
            return

        if cfg.args.incognito:
            logger.log("GHOST", f"Result: {safe_text}")
        else:
            logger.success(f"Result: {safe_text}")

        pyperclip.copy(safe_text)
        with self.kb.pressed(keyboard.Key.ctrl):
            self.kb.press("v")
            self.kb.release("v")

    async def shutdown(self):
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        await self.transport.disconnect(reason="App shutdown")
        self.audio.stop_stream()
