"""
Shared fixtures for the WhisperDoc terminal client test suite.

ConfigService is a module-level singleton that triggers argparse and
dotenv at import time. We patch it before any whisper_shell module
is imported by the test process.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Lightweight stub for ConfigService — replaces the real singleton so that
# importing whisper_shell.* never touches argparse, dotenv, or the filesystem.
# ---------------------------------------------------------------------------


def _build_stub_cfg():
    cfg = MagicMock()
    cfg.WS_URI = "ws://localhost:9989/ws"
    cfg.RECORD_HOTKEY = "ctrl+alt+w"
    cfg.AUDIO_DEVICE_ID = 0
    cfg.LOG_LEVEL = "INFO"
    cfg.VERSION = "2.23.5"
    cfg.IDLE_TIMEOUT = 300
    cfg.ENV_PATH = MagicMock()
    cfg.ENV_PATH.exists.return_value = True

    args = MagicMock()
    args.version = False
    args.clear_key = False
    args.setup = False
    args.health = False
    args.incognito = False
    cfg.args = args
    return cfg


def _build_stub_sec_cfg():
    sec_cfg = MagicMock()
    sec_cfg.get_api_key.return_value = "test-api-key-000"
    return sec_cfg


# Inject stubs into the module cache BEFORE any whisper_shell import.
_config_mod = types.ModuleType("whisper_shell.services.config_service")
setattr(_config_mod, "cfg", _build_stub_cfg())
setattr(_config_mod, "sec_cfg", _build_stub_sec_cfg())
setattr(_config_mod, "ConfigService", MagicMock)
setattr(_config_mod, "SecureConfigService", MagicMock)
setattr(_config_mod, "SERVICE_NAME", "WhisperDocTerminalClient")
setattr(_config_mod, "ENV_PATH", MagicMock())
sys.modules["whisper_shell.services.config_service"] = _config_mod


@pytest.fixture
def stub_cfg():
    """Returns a fresh stub cfg for tests that need to mutate it."""
    return _build_stub_cfg()


@pytest.fixture
def stub_sec_cfg():
    """Returns a fresh stub sec_cfg for tests that need to mutate it."""
    return _build_stub_sec_cfg()
