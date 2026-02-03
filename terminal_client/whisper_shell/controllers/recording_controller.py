import asyncio
import pyperclip
import json
from loguru import logger
from colorama import Fore, Style
from pynput import keyboard

from ..services.audio_service import AudioService
from ..services.transport_service import TransportService
from ..services.config_service import cfg
from ..logic.audio_buffer import AudioBufferManager
from ..logic.handshake import HandshakeState

class RecordingController:
    """
    Orchestrates the recording lifecycle.
    Bridges Transport, Audio, and UI logic (paste).
    """
    def __init__(self, loop):
        self.loop = loop
        self.audio_queue = asyncio.Queue()
        
        # Services
        self.audio = AudioService(loop, self.audio_queue)
        self.transport = TransportService()
        
        # Logic
        self.buffer_manager = AudioBufferManager()
        self.kb = keyboard.Controller()
        
        # State
        self.is_recording = False
        
        # Wire up transport listeners
        self.transport.add_message_listener(self._handle_server_message)
        self.transport.handshake.add_listener(self._on_handshake_state_changed)

    async def toggle_recording(self):
        """Main entry point triggered by Hotkey."""
        if not self.is_recording:
            await self._start_recording_session()
        else:
            await self._stop_recording_session()

    async def _start_recording_session(self):
        if self.is_recording: return
        
        self.is_recording = True
        logger.info(f"{Fore.CYAN}Recording...{Style.RESET_ALL}")
        
        # 1. Start Hardware Capture Instantly (Zero-Latency)
        self.audio.start_capture()
        
        # 2. Reset Buffer for new session
        self.buffer_manager.clear()
        
        # 3. Ensure Transport is connected in background (Auto-Wake)
        # We don't await this because we want to keep capturing audio
        asyncio.create_task(self.transport.ensure_connected())

        # 4. Start the Pipe loop
        asyncio.create_task(self._process_audio_pipe())

    async def _stop_recording_session(self):
        if not self.is_recording: return
        
        self.is_recording = False
        self.audio.stop_capture()
        logger.info(f"{Fore.CYAN}Stopped. Processing...{Style.RESET_ALL}")
        
        # Send end signal if we have a socket
        if self.transport.handshake.state == HandshakeState.AUTHENTICATED:
            await self.transport._send_json({"event": "end-of-stream"})

    async def _process_audio_pipe(self):
        """
        Continuously pulls data from audio queue and directs it to 
        the Buffer or the Socket depending on handshake state.
        """
        while self.is_recording or not self.audio_queue.empty():
            try:
                # Poll queue
                chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.1)
                
                if self.transport.handshake.state == HandshakeState.AUTHENTICATED:
                    # Flush buffer first if this is the first chunk after auth
                    if not self.buffer_manager.is_empty:
                        await self.buffer_manager.flush(self.transport.send_audio)
                    
                    await self.transport.send_audio(chunk)
                else:
                    # Handshake in progress or not connected yet -> Buffer it
                    self.buffer_manager.add(chunk)
                    
            except asyncio.TimeoutError:
                if not self.is_recording: break
            except Exception as e:
                logger.error(f"Audio pipe error: {e}")
                break

    async def _on_handshake_state_changed(self, state):
        """Triggers buffer flush when authentication completes."""
        if state == HandshakeState.AUTHENTICATED:
            # We flush in a separate task or within the pipe loop. 
            # Pipe loop is safer to ensure ordering.
            logger.debug("Handshake Authenticated. Pipe loop will flush buffer.")
        elif state == HandshakeState.FAILED:
            logger.error("Handshake failed. Clearing audio buffer.")
            self.buffer_manager.clear()

    async def _handle_server_message(self, msg: dict):
        """Processes transcription results and server errors."""
        event = msg.get("event")
        
        # 1. Handle Transcription Results
        if "text" in msg:
            text = msg["text"]
            self._paste_text(text)
        
        # 2. Handle Errors
        elif event == "error":
            logger.error(f"Server Error: {msg.get('code')} - {msg.get('message')}")
        
        # 3. Handle Status Updates
        elif event == "status":
            logger.info(f"Server Status: {msg.get('message')}")

    def _paste_text(self, text: str):
        if not text or not text.strip(): return
        
        from ..logic.sanitizer import Sanitizer
        safe_text = Sanitizer.sanitize(text)
        if not safe_text: return

        if cfg.args.incognito:
             logger.log("GHOST", f"Result: {safe_text}")
        else:
            logger.success(f"Result: {safe_text}")
        
        pyperclip.copy(safe_text)
        # Native simulate paste
        with self.kb.pressed(keyboard.Key.ctrl):
            self.kb.press('v')
            self.kb.release('v')

    async def shutdown(self):
        await self.transport.disconnect(reason="App shutdown")
        self.audio.stop_stream()
