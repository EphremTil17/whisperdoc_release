"""
Tests for the HandshakeStateMachine.

Pure state-machine logic — no I/O, no mocking required.
"""

import asyncio

import pytest
from whisper_shell.logic.handshake import HandshakeState, HandshakeStateMachine

# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_starts_locked(self):
        sm = HandshakeStateMachine()
        assert sm.state == HandshakeState.LOCKED

    def test_cannot_send_audio_when_locked(self):
        sm = HandshakeStateMachine()
        assert sm.can_send_audio() is False

    def test_error_context_starts_none(self):
        sm = HandshakeStateMachine()
        assert sm.last_error_code is None
        assert sm.last_message is None


# ---------------------------------------------------------------------------
# Happy path: LOCKED → AUTHENTICATING → AUTHENTICATED
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_locked_to_authenticating(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        assert sm.state == HandshakeState.AUTHENTICATING

    def test_authenticating_to_authenticated(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.AUTHENTICATED)
        assert sm.state == HandshakeState.AUTHENTICATED

    def test_can_send_audio_when_authenticated(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.AUTHENTICATED)
        assert sm.can_send_audio() is True

    def test_authenticated_to_locked_via_reset(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.AUTHENTICATED)
        sm.reset()
        assert sm.state == HandshakeState.LOCKED
        assert sm.can_send_audio() is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_authenticating_to_failed(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.FAILED)
        assert sm.state == HandshakeState.FAILED

    def test_locked_to_failed(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.FAILED)
        assert sm.state == HandshakeState.FAILED

    def test_failed_to_locked_via_reset(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.FAILED)
        sm.reset()
        assert sm.state == HandshakeState.LOCKED

    def test_banned_reachable_from_authenticating(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.BANNED)
        assert sm.state == HandshakeState.BANNED

    def test_banned_reachable_from_locked(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.BANNED)
        assert sm.state == HandshakeState.BANNED

    def test_version_outdated_reachable_from_authenticating(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.VERSION_OUTDATED)
        assert sm.state == HandshakeState.VERSION_OUTDATED

    def test_version_outdated_reachable_from_locked(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.VERSION_OUTDATED)
        assert sm.state == HandshakeState.VERSION_OUTDATED

    def test_cannot_send_audio_when_failed(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.FAILED)
        assert sm.can_send_audio() is False

    def test_cannot_send_audio_when_banned(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.BANNED)
        assert sm.can_send_audio() is False

    def test_cannot_send_audio_when_version_outdated(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.VERSION_OUTDATED)
        assert sm.can_send_audio() is False


# ---------------------------------------------------------------------------
# Invalid transitions are silently rejected
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_authenticated_to_failed_is_invalid(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.AUTHENTICATED)
        sm.transition_to(HandshakeState.FAILED)
        assert sm.state == HandshakeState.AUTHENTICATED

    def test_locked_to_authenticated_is_invalid(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATED)
        assert sm.state == HandshakeState.LOCKED

    def test_duplicate_transition_is_noop(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.AUTHENTICATING)
        assert sm.state == HandshakeState.AUTHENTICATING


# ---------------------------------------------------------------------------
# Error context
# ---------------------------------------------------------------------------


class TestErrorContext:
    def test_set_and_read_error_context(self):
        sm = HandshakeStateMachine()
        sm.set_error_context("AUTH_FAILED", "Invalid API key")
        assert sm.last_error_code == "AUTH_FAILED"
        assert sm.last_message == "Invalid API key"

    def test_reset_clears_error_context(self):
        sm = HandshakeStateMachine()
        sm.set_error_context("IP_BANNED", "Banned for 300s")
        sm.transition_to(HandshakeState.BANNED)
        sm.reset()
        assert sm.last_error_code is None
        assert sm.last_message is None


# ---------------------------------------------------------------------------
# Listeners
# ---------------------------------------------------------------------------


class TestListeners:
    def test_sync_listener_fires(self):
        sm = HandshakeStateMachine()
        states = []
        sm.add_listener(lambda s: states.append(s))
        sm.transition_to(HandshakeState.AUTHENTICATING)
        assert states == [HandshakeState.AUTHENTICATING]

    def test_listener_not_called_on_invalid_transition(self):
        sm = HandshakeStateMachine()
        states = []
        sm.add_listener(lambda s: states.append(s))
        sm.transition_to(HandshakeState.AUTHENTICATED)  # invalid from LOCKED
        assert states == []

    def test_listener_not_called_on_duplicate(self):
        sm = HandshakeStateMachine()
        sm.transition_to(HandshakeState.AUTHENTICATING)
        states = []
        sm.add_listener(lambda s: states.append(s))
        sm.transition_to(HandshakeState.AUTHENTICATING)  # same state
        assert states == []


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_transitions_to_failed(self):
        sm = HandshakeStateMachine(timeout=0.05)
        sm.transition_to(HandshakeState.AUTHENTICATING)
        await asyncio.sleep(0.1)
        assert sm.state == HandshakeState.FAILED
        assert sm.last_message == "Handshake timed out"

    @pytest.mark.asyncio
    async def test_timeout_cancelled_on_authenticated(self):
        sm = HandshakeStateMachine(timeout=0.1)
        sm.transition_to(HandshakeState.AUTHENTICATING)
        sm.transition_to(HandshakeState.AUTHENTICATED)
        await asyncio.sleep(0.15)
        assert sm.state == HandshakeState.AUTHENTICATED
