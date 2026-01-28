import asyncio
import sys
import time
import json
import pyperclip
import websockets
from pynput import keyboard
from loguru import logger
from colorama import Fore, Style

from .config import cfg, SecureConfig
from .audio import AudioManager
from .transport import TransportManager
from .input import HotkeyManager
from .utils import acquire_single_instance_lock, release_single_instance_lock, setup_interactive

class DictationClient:
    def __init__(self):
        self._check_setup()
        
        # Acquire single-instance lock (Mutex)
        self.instance_lock = acquire_single_instance_lock()
        if self.instance_lock is None:
            sys.exit(1) # Another instance is running
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.audio_queue = asyncio.Queue()
        self.audio = AudioManager(self.loop, self.audio_queue)
        self.transport = TransportManager()
        self.hotkey = HotkeyManager(self.toggle_recording)
        self.kb = keyboard.Controller()
        
        self.is_running = True

    def _check_setup(self):
        if cfg.args.version:
            logger.info(f"WhisperDoc Terminal Client v{cfg.VERSION}")
            sys.exit(0)

        if cfg.args.clear_key:
            # We need to know the host to clear the key
            # Re-use transport logic to parse URI
            from .transport import TransportManager
            tm = TransportManager() # This will log the URI, acceptable
            SecureConfig.clear_key(tm.hostname)
            logger.success(f"API Key for {tm.hostname} cleared.")
            sys.exit(0)

        if not cfg.ENV_PATH.exists() or cfg.args.setup:
            setup_interactive()
            # Reload env after setup
            cfg._load_env()
        
        if cfg.args.health:
            tm = TransportManager() # Temp instance for check
            if tm.check_health(): sys.exit(0)
            else: sys.exit(1)

    def toggle_recording(self):
        if not self.audio.is_recording:
            self.audio.start_recording()
            logger.info(f"{Fore.CYAN}Recording...{Style.RESET_ALL}")
        else:
            self.audio.stop_recording()
            logger.info(f"{Fore.CYAN}Stopped. Processing...{Style.RESET_ALL}")

    def paste_text(self, text):
        if not text or not text.strip(): return
        
        if cfg.args.incognito:
             logger.log("GHOST", f"Result: {text}")
        else:
            logger.success(f"Result: {text}")
        
        pyperclip.copy(text)
        with self.kb.pressed(keyboard.Key.ctrl):
            self.kb.press('v')
            self.kb.release('v')

    async def _main_loop(self):
        IDLE_TIMEOUT = 300
        last_activity = time.time()

        while self.is_running:
            try:
                # 1. Connection Management
                if not self.transport.ws:
                    if self.audio.is_recording: # Connect on demand
                        await self.transport.connect()
                        last_activity = time.time()
                
                # 2. Audio Streaming
                if self.audio.is_recording and self.transport.ws:
                    while self.audio.is_recording or not self.audio_queue.empty():
                        try:
                            # Send chunks
                            chunk = await asyncio.wait_for(self.audio_queue.get(), 0.05)
                            await self.transport.send(chunk)
                            last_activity = time.time()
                        except asyncio.TimeoutError:
                            if not self.audio.is_recording: break
                    
                    # End of Stream
                    await self.transport.send('{"event": "end-of-stream"}')
                    
                    # 3. Receive Results
                    while True:
                        msg = await self.transport.recv()
                        resp = json.loads(msg)
                        
                        if resp.get("event") == "status":
                             logger.info(f"Server Status: {resp.get('message')}")
                             continue
                        
                        if "text" in resp:
                             self.paste_text(resp["text"])
                             break
                        
                        if resp.get("event") == "error":
                             code = resp.get("code")
                             msg = resp.get("message")
                             logger.error(f"Server: {code} - {msg}")
                             
                             if code == "NO_AUDIO":
                                 logger.warning(f"{Fore.YELLOW}Tip: Check your microphone connection and settings.{Style.RESET_ALL}")
                             break
                    last_activity = time.time()

                # 4. Idle Timeout
                if self.transport.ws and (time.time() - last_activity > IDLE_TIMEOUT):
                     logger.info("Idle timeout. Disconnecting.")
                     await self.transport.close()

                await asyncio.sleep(0.05)

            except Exception as e:
                # Standardize Auth Failure checks
                is_auth = False
                if isinstance(e, websockets.exceptions.InvalidStatusCode):
                     if e.status_code in [401, 403]: is_auth = True
                elif isinstance(e, websockets.exceptions.ConnectionClosed):
                     if e.code == 1008: is_auth = True
                elif "Auth Failed" in str(e):
                     is_auth = True
                
                if is_auth:
                     logger.error(f"{Fore.RED}Authentication Failed.{Style.RESET_ALL} Invalid Key.")
                     SecureConfig.clear_key(self.transport.hostname)
                     await self.transport.close()
                     self.is_running = False # Terminate client immediately
                     break
                else:
                     logger.error(f"Loop Error: {e}")
                     await self.transport.close()
                     await asyncio.sleep(1)

    async def _verify_auth_and_connect(self):
        """
        Attempts to connect and verify credentials with exponential backoff.
        Handles transient failures (e.g., OIDC warmup race) gracefully.
        """
        MAX_RETRIES = 3
        
        for attempt in range(MAX_RETRIES):
            try:
                await self.transport.connect()
                # Keep connection open for immediate use
                return True
            except Exception as e:
                # Standardize Auth Failure checks
                is_auth = False
                if isinstance(e, websockets.exceptions.InvalidStatusCode):
                    if e.status_code in [401, 403]: is_auth = True
                elif isinstance(e, websockets.exceptions.ConnectionClosed):
                    if e.code == 1008: is_auth = True
                elif "HTTP 403" in str(e) or "HTTP 401" in str(e) or "Auth Failed" in str(e): 
                    is_auth = True

                if is_auth:
                    logger.error(f"{Fore.RED}Startup Auth Failed.{Style.RESET_ALL} Server rejected the key.")
                    SecureConfig.clear_key(self.transport.hostname)
                    return False
                else:
                    # Transient error - retry with backoff
                    if attempt < MAX_RETRIES - 1:
                        wait_time = 2 ** attempt  # 1s, 2s, 4s
                        logger.warning(f"Connection attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning(f"Startup Connection Failed after {MAX_RETRIES} attempts: {e}. Proceeding anyway.")
                        return True  # Allow proceeding after exhausting retries

    def start(self):
        # 1. Enforce Auth Upfront
        fqdn = self.transport.hostname
        
        # This will block until the user enters a key or we find one
        key = SecureConfig.get_api_key(fqdn)
        if not key:
            logger.error("No API Key provided. Exiting.")
            return

        # 2. VALIDATE the key against the server
        # We run a single async check before starting fully
        if not self.loop.run_until_complete(self._verify_auth_and_connect()):
             logger.error("Aborting startup due to invalid credentials.")
             return

        # 3. Start Audio Stream (before hotkey so we're fully ready)
        self.audio.start_stream()
        
        if cfg.args.incognito:
             logger.warning(f"Ghost Mode Active: Remote logs are sanitized.")
        
        # 4. Start Hotkey Service (last, so everything is ready when user presses it)
        self.hotkey.start()
        logger.success(f"Client Ready. Hotkey: {cfg.RECORD_HOTKEY}")
        
        try:
            self.loop.run_until_complete(self._main_loop())
        except KeyboardInterrupt:
            pass
        finally:
            self.audio.stop_stream()
            self.hotkey.stop()
            release_single_instance_lock(self.instance_lock)
            logger.info("Shutting down.")
