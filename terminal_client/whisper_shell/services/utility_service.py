import os

import sounddevice as sd
from dotenv import set_key
from loguru import logger

from .config_service import SERVICE_NAME, cfg


def acquire_single_instance_lock():
    """
    Acquires a system-wide mutex to ensure only one instance runs.
    Returns the mutex handle if acquired, or None if another instance is running.
    """
    if os.name != "nt":
        return True  # Runtime entrypoint rejects unsupported non-Windows launches

    import ctypes

    MUTEX_NAME = "Global\\WhisperDocClientMutex"
    ERROR_ALREADY_EXISTS = 183

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        logger.warning(
            "Another instance of WhisperDoc Client is already running. Exiting."
        )
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
    if handle and handle is not True and os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.ReleaseMutex(handle)
        ctypes.windll.kernel32.CloseHandle(handle)


def _prompt_audio_api(api_map, fore, style) -> str | None:
    """Prompt user to select an audio API. Returns the API name or None for 'All'."""
    while True:
        print("\nSelect Audio API:")
        print(" [1] WASAPI (Best) | [2] DirectSound | [3] MME | [0] All")
        api_choice = input("Choice [1]: ").strip() or "1"
        if api_choice in api_map:
            return api_map[api_choice]
        print(
            f"{fore.RED}Invalid choice. Please select from 0, 1, 2, or 3.{style.RESET_ALL}"
        )


def _list_input_devices(
    target_api: str | None, devices, host_apis, default_input
) -> list[int]:
    """Print available input devices filtered by API and return their IDs."""
    valid_ids = []
    print(f"\nAvailable Input Devices ({target_api or 'All'}):")
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] <= 0:
            continue
        api_name = host_apis[dev["hostapi"]]["name"]
        if target_api and api_name != target_api:
            continue
        valid_ids.append(i)
        marker = " (DEFAULT)" if i == default_input else ""
        print(f" [{i}] {dev['name']} | {api_name}{marker}")
    return valid_ids


def _prompt_audio_device(target_api, api_map, fore, style) -> int:
    """Prompt user to select an audio input device. Returns the device ID."""
    devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    default_input = sd.query_hostapis()[0].get("default_input")

    while True:
        valid_ids = _list_input_devices(target_api, devices, host_apis, default_input)

        if not valid_ids:
            print(
                f"{fore.RED}No devices found for the selected API. Please choose another API.{style.RESET_ALL}"
            )
            target_api = _prompt_audio_api(api_map, fore, style)
            continue

        device_id_str = input(
            f"\nSelect Device ID [{valid_ids[0] if valid_ids else 'None'}]: "
        ).strip() or str(valid_ids[0])
        try:
            device_id = int(device_id_str)
            if device_id in valid_ids:
                return device_id
            print(
                f"{fore.RED}Invalid Device ID {device_id}. Please choose from the list above.{style.RESET_ALL}"
            )
        except ValueError:
            print(f"{fore.RED}Please enter a numeric Device ID.{style.RESET_ALL}")


def _save_setup_config(uri: str, device_id: int) -> None:
    """Write setup configuration to .env and reload."""
    if not cfg.ENV_PATH.exists():
        cfg.ENV_PATH.touch()
    set_key(str(cfg.ENV_PATH), "WHISPER_WS_URI", uri)
    set_key(str(cfg.ENV_PATH), "AUDIO_DEVICE_ID", str(device_id))
    set_key(str(cfg.ENV_PATH), "RECORD_HOTKEY", "ctrl+alt+w")
    set_key(str(cfg.ENV_PATH), "LOG_LEVEL", "INFO")
    set_key(str(cfg.ENV_PATH), "IDLE_TIMEOUT", "300")
    cfg._load_env()


def _prompt_api_key_reset(host: str) -> None:
    """Check for existing API key and prompt user to reset if found."""
    import keyring

    if keyring.get_password(SERVICE_NAME, host):
        reset = (
            input(f"\nExisting API Key found for {host}. Reset it? [y/N]: ")
            .strip()
            .lower()
        )
        if reset == "y":
            keyring.delete_password(SERVICE_NAME, host)
            logger.info(f"API Key for {host} cleared.")


def setup_interactive():
    """Minimal interactive setup for first-run configuration."""
    from urllib.parse import urlparse

    from colorama import Fore, Style

    logger.info("--- WhisperDoc Client Setup ---")

    uri = input(f"Enter Server WebSocket URI [{cfg.WS_URI}]: ").strip() or cfg.WS_URI
    api_map = {"1": "Windows WASAPI", "2": "Windows DirectSound", "3": "MME", "0": None}

    target_api = _prompt_audio_api(api_map, Fore, Style)
    device_id = _prompt_audio_device(target_api, api_map, Fore, Style)
    _save_setup_config(uri, device_id)
    _prompt_api_key_reset(urlparse(uri).hostname or "localhost")

    logger.success("Setup complete. Default hotkey: ctrl+alt+w")
