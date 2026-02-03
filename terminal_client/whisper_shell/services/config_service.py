import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import keyring
from getpass import getpass
from loguru import logger
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init()

SERVICE_NAME = "WhisperDoc_Client"
ENV_PATH = Path(".env")
DEFAULT_VERSION = "2.20.0"

class ConfigService:
    """
    Configuration Service managing environment variables and CLI arguments.
    """
    def __init__(self):
        self.ENV_PATH = ENV_PATH
        self._load_env()
        self._parse_args()
        self._setup_logging()

    def _load_env(self):
        load_dotenv(ENV_PATH, override=True)
        self.WS_URI = os.getenv("WHISPER_WS_URI", "ws://localhost:9989/ws")
        self.RECORD_HOTKEY = os.getenv("RECORD_HOTKEY", "ctrl+alt+w")
        self.AUDIO_DEVICE_ID = int(os.getenv("AUDIO_DEVICE_ID", 0))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.VERSION = os.getenv("CLIENT_VERSION", DEFAULT_VERSION)
        self.IDLE_TIMEOUT = int(os.getenv("IDLE_TIMEOUT", 300))

    def _parse_args(self):
        parser = argparse.ArgumentParser(description="WhisperDoc Terminal Client")
        parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
        parser.add_argument("--health", action="store_true", help="Run pre-flight server health check")
        parser.add_argument("--version", action="store_true", help="Print client version and exit")
        parser.add_argument("--clear-key", action="store_true", help="Clear stored API key and exit")
        parser.add_argument("--incognito", action="store_true", help="Enable Ghost Mode (No server logs, no local history)")
        self.args = parser.parse_known_args()[0]

    def _setup_logging(self):
        logger.remove()
        try:
            # Custom log level for Incognito (Ghost) mode
            logger.level("GHOST", no=25, color="<magenta>")
        except TypeError:
            pass
            
        logger.add(
            sys.stdout, 
            level=self.LOG_LEVEL, 
            format="<white>{time:HH:mm:ss}</white> | <level>{level: <8}</level> | <white>{message}</white>"
        )

class SecureConfigService:
    """
    Secure Configuration Service for managing credentials in OS Keyring.
    """
    @staticmethod
    def get_api_key(host: str) -> str:
        key = keyring.get_password(SERVICE_NAME, host)
        if key:
            return key
        
        print(f"{Fore.YELLOW}Authentication Required for {host}{Style.RESET_ALL}")
        try:
             key = getpass(f"Enter API Key for {host}: ").strip()
        except Exception:
             key = input(f"Enter API Key for {host}: ").strip()
             
        if key:
            keyring.set_password(SERVICE_NAME, host, key)
            print(f"{Fore.GREEN}Key saved securely to OS keyring.{Style.RESET_ALL}")
            return key
        return ""

    @staticmethod
    def clear_key(host: str):
        try:
            keyring.delete_password(SERVICE_NAME, host)
            logger.warning(f"Invalid API Key removed from secure storage for {host}.")
        except keyring.errors.PasswordDeleteError:
            pass 

# Singleton instance for easy access
cfg = ConfigService()
sec_cfg = SecureConfigService()
