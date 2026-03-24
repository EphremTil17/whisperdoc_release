"""
Tests for HotkeyService._parse_hk() — hotkey string parser.

The Win32 message loop and pynput listener are hardware/OS-bound
and not unit-testable, but the parser is pure logic.
"""

from whisper_shell.services.hotkey_service import HotkeyService


def _parse(s: str):
    svc = HotkeyService(callback=lambda: None)
    return svc._parse_hk(s)


class TestParseHotkey:
    def test_ctrl_alt_w(self):
        mods, vk = _parse("ctrl+alt+w")
        assert mods == 0x0002 | 0x0001  # MOD_CONTROL | MOD_ALT
        assert vk == ord("W")

    def test_single_fkey(self):
        mods, vk = _parse("f9")
        assert mods == 0
        assert vk == 0x6F + 9  # VK_F9

    def test_shift_f1(self):
        mods, vk = _parse("shift+f1")
        assert mods == 0x0004  # MOD_SHIFT
        assert vk == 0x6F + 1  # VK_F1

    def test_ctrl_shift_alt_del(self):
        mods, vk = _parse("ctrl+shift+alt+del")
        assert mods == 0x0002 | 0x0004 | 0x0001
        assert vk == 0x2E  # VK_DELETE

    def test_win_space(self):
        mods, vk = _parse("win+space")
        assert mods == 0x0008  # MOD_WIN
        assert vk == 0x20  # VK_SPACE

    def test_single_letter(self):
        mods, vk = _parse("a")
        assert mods == 0
        assert vk == ord("A")

    def test_case_insensitive(self):
        mods1, vk1 = _parse("Ctrl+Alt+W")
        mods2, vk2 = _parse("ctrl+alt+w")
        assert mods1 == mods2
        assert vk1 == vk2

    def test_insert_key(self):
        _, vk = _parse("ins")
        assert vk == 0x2D  # VK_INSERT

    def test_unknown_token_ignored(self):
        mods, vk = _parse("ctrl+banana+r")
        assert mods == 0x0002
        assert vk == ord("R")
