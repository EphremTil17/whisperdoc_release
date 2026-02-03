import asyncio
import sys
from loguru import logger

from .services.config_service import cfg, sec_cfg
from .services.hotkey_service import HotkeyService
from .services.utility_service import (
    acquire_single_instance_lock, 
    release_single_instance_lock, 
    setup_interactive
)
from .controllers.recording_controller import RecordingController

class DictationClient:
    """
    Main entry point for the WhisperDoc Terminal Client.
    Manages initialization, lifecycle, and hotkey wiring.
    """
    def __init__(self):
        self._check_setup()
        
        # 1. Instance Protection
        self.instance_lock = acquire_single_instance_lock()
        if self.instance_lock is None:
            sys.exit(1)
            
        # 2. Async Lifecycle
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 3. Controller & Services
        self.controller = RecordingController(self.loop)
        self.hotkey = HotkeyService(self._on_hotkey)
        
        self.is_running = True

    def _check_setup(self):
        """CLI arguments and first-run setup."""
        if cfg.args.version:
            logger.info(f"WhisperDoc Terminal Client v{cfg.VERSION}")
            sys.exit(0)

        if cfg.args.clear_key:
            sec_cfg.clear_key(self.controller.transport.hostname)
            sys.exit(0)

        if not cfg.ENV_PATH.exists() or cfg.args.setup:
            setup_interactive()
        
        if cfg.args.health:
            if self.controller.transport.check_health(): 
                sys.exit(0)
            else: 
                sys.exit(1)

    def _on_hotkey(self):
        """Bridge between threaded hotkey listener and async controller."""
        asyncio.run_coroutine_threadsafe(
            self.controller.toggle_recording(), 
            self.loop
        )

    def start(self):
        """Starts the client lifecycle."""
        # 1. Verify Credentials
        key = sec_cfg.get_api_key(self.controller.transport.hostname)
        if not key:
            logger.error("No API Key provided. Aborting.")
            return

        # 2. Warm up Audio Hardware
        try:
            self.controller.audio.start_stream()
        except Exception:
            return

        # 3. Proactive Connection (Launch Auth)
        # We start the background handshake immediately to wake the server
        logger.info("Proactively warming up backend connection...")
        asyncio.run_coroutine_threadsafe(
            self.controller.transport.connect(), 
            self.loop
        )

        # 4. Start Hotkey Service
        self.hotkey.start()
        logger.success(f"Client Ready. Hotkey: {cfg.RECORD_HOTKEY}")
        
        # 4. Run Async Event Loop
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Robust cleanup and memory hygiene."""
        if not self.is_running: return
        
        logger.info("Initiating robust shutdown...")
        self.is_running = False
        self.hotkey.stop()
        
        # Shutdown async services
        if self.loop.is_running():
            # Schedule disconnect and wait for a brief moment for it to complete
            stop_task = asyncio.run_coroutine_threadsafe(
                self.controller.shutdown(), 
                self.loop
            )
            try:
                stop_task.result(timeout=2.0)
            except Exception as e:
                logger.warning(f"Shutdown task timed out or failed: {e}")
            
            self.loop.stop()
            
        release_single_instance_lock(self.instance_lock)
        logger.success("Shutdown complete. Memory and processes freed.")
