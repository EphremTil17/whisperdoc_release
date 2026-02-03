import os
import threading
import ctypes
from pynput import keyboard
from loguru import logger
from ..services.config_service import cfg

class HotkeyService:
    """
    Service managing global OS-level hotkeys.
    Uses native Win32 API for Windows (reliability) and pynput for others.
    """
    def __init__(self, callback):
        self.callback = callback
        self.running = True
        self.thread = None

    def _parse_hk(self, s):
        """Maps human-readable hotkey string to Win32 modifiers and VK codes."""
        mods, vk = 0, 0
        mod_map = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
        vk_map = {f"f{i}": 0x6F+i for i in range(1, 13)}
        vk_map.update({"ins": 0x2D, "del": 0x2E, "space": 0x20})
        for p in s.split("+"):
            p = p.strip().lower()
            if p in mod_map: 
                mods |= mod_map[p]
            elif p in vk_map: 
                vk = vk_map[p]
            elif len(p) == 1: 
                vk = ord(p.upper())
        return mods, vk

    def _windows_loop(self):
        """Native Windows Message Loop for hotkey capture."""
        try:
            user32 = ctypes.windll.user32
            from ctypes import wintypes
            
            m, v = self._parse_hk(cfg.RECORD_HOTKEY)
            
            # Register Global Hotkey (ID 1)
            if not user32.RegisterHotKey(None, 1, m, v):
                logger.error(f"Failed to register hotkey {cfg.RECORD_HOTKEY}. Is it already in use?")
                return

            logger.info(f"Hotkey Active (Win32): {cfg.RECORD_HOTKEY}")
            msg = wintypes.MSG()
            while self.running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
                if msg.message == 0x0312: # WM_HOTKEY
                     logger.debug("Hotkey Triggered.")
                     self.callback()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                
            user32.UnregisterHotKey(None, 1)
        except Exception as e:
            logger.error(f"Native Hotkey Loop Error: {e}")

    def start(self):
        """Initiates the hotkey listener."""
        if os.name == 'nt':
            self.thread = threading.Thread(target=self._windows_loop, daemon=True)
            self.thread.start()
        else:
            # Fallback for non-Windows platforms
            hk_str = f"<{cfg.RECORD_HOTKEY.replace('+', '><')}>"
            hk = {hk_str : self.callback}
            self.listener = keyboard.GlobalHotKeys(hk)
            self.listener.start()
            logger.info(f"Hotkey Active (pynput): {hk_str}")

    def stop(self):
        """Shutdown listeners."""
        self.running = False
        if os.name != 'nt' and hasattr(self, 'listener'):
            self.listener.stop()
        logger.info("Hotkey Service Stopped.")
