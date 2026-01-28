import os
import sys
import time
import subprocess
import sounddevice as sd
from loguru import logger
from dotenv import set_key
from .config import cfg

def acquire_single_instance_lock():
    """
    Acquires a system-wide mutex to ensure only one instance runs.
    Returns the mutex handle if acquired, or None if another instance is running.
    Uses Windows Mutex API via ctypes.
    """
    import ctypes
    from ctypes import wintypes

    MUTEX_NAME = "Global\\WhisperDocClientMutex"
    ERROR_ALREADY_EXISTS = 183

    kernel32 = ctypes.windll.kernel32
    
    # CreateMutexW(lpMutexAttributes, bInitialOwner, lpName)
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        logger.warning("Another instance of WhisperDoc Client is already running. Exiting.")
        if handle:
            kernel32.CloseHandle(handle)
        return None
    
    if not handle:
        logger.warning("Could not create instance lock. Proceeding anyway.")
        return None # Proceed without lock (non-fatal)

    logger.debug("Instance lock acquired.")
    return handle

def release_single_instance_lock(handle):
    """Releases the mutex handle."""
    if handle:
        import ctypes
        ctypes.windll.kernel32.ReleaseMutex(handle)
        ctypes.windll.kernel32.CloseHandle(handle)

def setup_interactive():
    """Minimal interactive setup for first-run configuration."""
    logger.info("--- WhisperDoc Client Setup ---")
    
    current_uri = cfg.WS_URI
    uri = input(f"Enter Server WebSocket URI [{current_uri}]: ").strip() or current_uri
    
    print("\nSelect Audio API:")
    print(" [1] WASAPI (Best) | [2] DirectSound | [3] MME | [0] All")
    api_choice = input("Choice [1]: ").strip() or "1"
    api_map = {"1": "Windows WASAPI", "2": "Windows DirectSound", "3": "MME", "4": "Windows WDM-KS"}
    target_api = api_map.get(api_choice)

    devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    default_input = sd.query_hostapis()[0].get('default_input')
    
    print(f"\nAvailable Input Devices ({target_api or 'All'}):")
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            api_name = host_apis[dev['hostapi']]['name']
            if target_api and api_name != target_api: continue
            marker = " (DEFAULT)" if i == default_input else ""
            print(f" [{i}] {dev['name']} | {api_name}{marker}")
    
    device_id = input(f"\nSelect Device ID [{default_input}]: ").strip() or str(default_input)
    
    if not cfg.ENV_PATH.exists(): cfg.ENV_PATH.touch()
    set_key(str(cfg.ENV_PATH), "WHISPER_WS_URI", uri)
    set_key(str(cfg.ENV_PATH), "AUDIO_DEVICE_ID", device_id)
    set_key(str(cfg.ENV_PATH), "RECORD_HOTKEY", "ctrl+alt+w")
    set_key(str(cfg.ENV_PATH), "SAMPLE_RATE", "16000")
    set_key(str(cfg.ENV_PATH), "CHANNELS", "1")
    set_key(str(cfg.ENV_PATH), "LOG_LEVEL", "INFO")
    
    # Ask to reset API Key
    from .config import SecureConfig, SERVICE_NAME
    import keyring
    
    parsed = __import__("urllib.parse").parse.urlparse(uri)
    host = parsed.hostname or "localhost"
    
    if keyring.get_password(SERVICE_NAME, host):
        reset = input(f"\nExisting API Key found for {host}. Reset it? [y/N]: ").strip().lower()
        if reset == 'y':
            SecureConfig.clear_key(host)
            logger.info(f"API Key for {host} cleared.")

    logger.success("Setup complete. Default hotkey: ctrl+alt+w")
    logger.info("To change hotkey, edit RECORD_HOTKEY in .env")
