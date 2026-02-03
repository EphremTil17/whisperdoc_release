import os
import sys
import sounddevice as sd
from loguru import logger
from dotenv import set_key
from .config_service import cfg, SERVICE_NAME

def acquire_single_instance_lock():
    """
    Acquires a system-wide mutex to ensure only one instance runs.
    Returns the mutex handle if acquired, or None if another instance is running.
    """
    if os.name != 'nt':
        return True # Non-Windows fallback simplifies for now

    import ctypes
    MUTEX_NAME = "Global\\WhisperDocClientMutex"
    ERROR_ALREADY_EXISTS = 183

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        logger.warning("Another instance of WhisperDoc Client is already running. Exiting.")
        if handle:
            kernel32.CloseHandle(handle)
        return None
    
    if not handle:
        logger.warning("Could not create instance lock. Proceeding anyway.")
        return True

    logger.debug("Instance lock acquired.")
    return handle

def release_single_instance_lock(handle):
    """Releases the mutex handle."""
    if handle and handle is not True and os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.ReleaseMutex(handle)
        ctypes.windll.kernel32.CloseHandle(handle)

def setup_interactive():
    """Minimal interactive setup for first-run configuration."""
    from urllib.parse import urlparse
    import keyring
    
    from colorama import Fore, Style

    logger.info("--- WhisperDoc Client Setup ---")
    
    current_uri = cfg.WS_URI
    uri = input(f"Enter Server WebSocket URI [{current_uri}]: ").strip() or current_uri
    
    # 1. API Selection Loop
    api_map = {"1": "Windows WASAPI", "2": "Windows DirectSound", "3": "MME", "0": None}
    while True:
        print("\nSelect Audio API:")
        print(" [1] WASAPI (Best) | [2] DirectSound | [3] MME | [0] All")
        api_choice = input("Choice [1]: ").strip() or "1"
        if api_choice in api_map:
            target_api = api_map[api_choice]
            break
        print(f"{Fore.RED}Invalid choice. Please select from 0, 1, 2, or 3.{Style.RESET_ALL}")

    # 2. Device Selection Loop
    devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    default_input = sd.query_hostapis()[0].get('default_input')
    
    while True:
        valid_ids = []
        print(f"\nAvailable Input Devices ({target_api or 'All'}):")
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                api_name = host_apis[dev['hostapi']]['name']
                if target_api and api_name != target_api: 
                    continue
                
                valid_ids.append(i)
                marker = " (DEFAULT)" if i == default_input else ""
                print(f" [{i}] {dev['name']} | {api_name}{marker}")
        
        if not valid_ids:
            print(f"{Fore.RED}No devices found for the selected API. Please choose another API.{Style.RESET_ALL}")
            # Reset API selection
            while True:
                print("\nSelect Audio API:")
                print(" [1] WASAPI (Best) | [2] DirectSound | [3] MME | [0] All")
                api_choice = input("Choice [1]: ").strip() or "1"
                if api_choice in api_map:
                    target_api = api_map[api_choice]
                    break
            continue

        device_id_str = input(f"\nSelect Device ID [{valid_ids[0] if valid_ids else 'None'}]: ").strip() or str(valid_ids[0])
        try:
            device_id = int(device_id_str)
            if device_id in valid_ids:
                break
            print(f"{Fore.RED}Invalid Device ID {device_id}. Please choose from the list above.{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}Please enter a numeric Device ID.{Style.RESET_ALL}")
    
    if not cfg.ENV_PATH.exists(): cfg.ENV_PATH.touch()
    set_key(str(cfg.ENV_PATH), "WHISPER_WS_URI", uri)
    set_key(str(cfg.ENV_PATH), "AUDIO_DEVICE_ID", str(device_id))
    set_key(str(cfg.ENV_PATH), "RECORD_HOTKEY", "ctrl+alt+w")
    set_key(str(cfg.ENV_PATH), "LOG_LEVEL", "INFO")
    set_key(str(cfg.ENV_PATH), "IDLE_TIMEOUT", "300")
    
    # Reload config
    cfg._load_env()
    
    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    
    if keyring.get_password(SERVICE_NAME, host):
        reset = input(f"\nExisting API Key found for {host}. Reset it? [y/N]: ").strip().lower()
        if reset == 'y':
            keyring.delete_password(SERVICE_NAME, host)
            logger.info(f"API Key for {host} cleared.")

    logger.success("Setup complete. Default hotkey: ctrl+alt+w")
