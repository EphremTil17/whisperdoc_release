import os
import threading
import ctypes
from pynput import keyboard
from loguru import logger
from .config import cfg

class HotkeyManager:
    def __init__(self, callback):
        self.callback = callback
        self.running = True
        self.thread = None

    def _parse_hk(self, s):
        mods, vk = 0, 0
        mod_map = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
        vk_map = {f"f{i}": 0x6F+i for i in range(1, 13)}
        vk_map.update({"ins": 0x2D, "del": 0x2E, "space": 0x20})
        for p in s.split("+"):
            p = p.strip()
            if p in mod_map: mods |= mod_map[p]
            elif p in vk_map: vk = vk_map[p]
            elif len(p) == 1: vk = ord(p.upper())
        return mods, vk

    def _windows_loop(self):
        try:
            user32 = ctypes.windll.user32
            from ctypes import wintypes
            
            m, v = self._parse_hk(cfg.RECORD_HOTKEY)
            
            # Register Global Hotkey
            if not user32.RegisterHotKey(None, 1, m, v):
                logger.error("Failed to register hotkey. It might be in use.")
                return

            msg = wintypes.MSG()
            while self.running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
                if msg.message == 0x0312: # WM_HOTKEY
                     self.callback()
            user32.UnregisterHotKey(None, 1)
        except Exception as e:
            logger.error(f"Hotkey Error: {e}")

    def start(self):
        if os.name == 'nt':
            self.thread = threading.Thread(target=self._windows_loop, daemon=True)
            self.thread.start()
        else:
            # Linux/Mac fallback (pynput)
            hk = {f"<{cfg.RECORD_HOTKEY.replace('+', '><')}>" : self.callback}
            self.listener = keyboard.GlobalHotKeys(hk)
            self.listener.start()

    def stop(self):
        self.running = False
        if os.name != 'nt' and hasattr(self, 'listener'):
            self.listener.stop()
