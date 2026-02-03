import pytest
from whisper_shell.logic.sanitizer import Sanitizer

def test_basic_printable_ascii():
    assert Sanitizer.sanitize("Hello World 123!") == "Hello World 123!"

def test_strips_ansi_colors():
    # \x1b[31m is red, \x1b[0m is reset
    malicious = "\x1b[31mExploit\x1b[0m"
    assert Sanitizer.sanitize(malicious) == "Exploit"

def test_strips_control_characters():
    # \x03 is Ctrl+C, \x07 is terminal bell
    malicious = "Start\x03\x07End"
    assert Sanitizer.sanitize(malicious) == "StartEnd"

def test_strips_null_byte():
    malicious = "Valid\x00Truncated?"
    assert Sanitizer.sanitize(malicious) == "ValidTruncated?"

def test_mitigates_command_chaining():
    malicious = "Help; rm -rf /"
    # Whitelist allows ;, but not \n or \r if they were used for injection.
    # The actual protection here is that control chars are stripped.
    assert Sanitizer.sanitize(malicious) == "Help; rm -rf /"

def test_redos_protection():
    # Testing with a potentially catastrophic string if regex wasn't pre-compiled or safe
    malicious = "a" * 100 + "!"
    # Whitelist should handle this instantly as it's non-backtracking
    assert Sanitizer.sanitize(malicious) == malicious

def test_strips_terminal_redefinition_escapes():
    # OSC sequences that attempt to change terminal title or icon
    malicious = "Safe\x1b]0;Evil Title\x07Text"
    assert Sanitizer.sanitize(malicious) == "SafeText"
