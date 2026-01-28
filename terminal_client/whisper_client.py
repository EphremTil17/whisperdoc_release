#!/usr/bin/env python3
"""
WhisperDoc Client - Bootstrap Script
Determines if run as script or module and launches the Modular Shell.
"""
import sys
from pathlib import Path

# Ensure client directory is in path so we can import whisper_shell
sys.path.append(str(Path(__file__).parent))

from whisper_shell import DictationClient

if __name__ == "__main__":
    try:
        DictationClient().start()
    except KeyboardInterrupt:
        pass
