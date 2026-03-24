"""
Tests for TransportService connection lifecycle, teardown, and keepalive.

Complements test_transport.py by covering the connect/disconnect flows
and the full reconnection state machine.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from whisper_shell.logic.handshake import HandshakeState
from whisper_shell.services.transport_service import TransportService

# ---------------------------------------------------------------------------
# Connect flow
# ---------------------------------------------------------------------------


class TestConnectFlow:
    @pytest.mark.asyncio
    async def test_connect_when_already_connected_returns_true(self):
        svc = TransportService()
        svc._ws = MagicMock()  # pretend already connected
        result = await svc.connect()
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_failure_schedules_reconnect(self):
        svc = TransportService()
        with patch(
            "whisper_shell.services.transport_service.websockets.connect",
            new_callable=AsyncMock,
            side_effect=OSError("refused"),
        ):
            result = await svc.connect()
        assert result is False
        assert svc._reconnect_task is not None
        svc._cancel_reconnect()

    @pytest.mark.asyncio
    async def test_connect_resets_intentional_disconnect_flag(self):
        svc = TransportService()
        svc._intentional_disconnect = True
        with patch(
            "whisper_shell.services.transport_service.websockets.connect",
            new_callable=AsyncMock,
            side_effect=OSError("refused"),
        ):
            await svc.connect()
        assert svc._intentional_disconnect is False


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_sets_intentional_flag(self):
        svc = TransportService()
        await svc.disconnect(reason="user action")
        assert svc._intentional_disconnect is True

    @pytest.mark.asyncio
    async def test_disconnect_resets_handshake(self):
        svc = TransportService()
        svc.handshake.transition_to(HandshakeState.AUTHENTICATING)
        svc.handshake.transition_to(HandshakeState.AUTHENTICATED)
        await svc.disconnect()
        assert svc.handshake.state == HandshakeState.LOCKED


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


class TestTeardown:
    @pytest.mark.asyncio
    async def test_teardown_cancels_keepalive(self):
        svc = TransportService()
        svc._keepalive_task = asyncio.create_task(asyncio.sleep(999))
        await svc._teardown("test")
        assert svc._keepalive_task is None

    @pytest.mark.asyncio
    async def test_teardown_cancels_idle_timer(self):
        svc = TransportService()
        svc._idle_timer = asyncio.create_task(asyncio.sleep(999))
        await svc._teardown("test")
        assert svc._idle_timer is None

    @pytest.mark.asyncio
    async def test_teardown_cancels_receive_task(self):
        svc = TransportService()
        svc._receive_task = asyncio.create_task(asyncio.sleep(999))
        await svc._teardown("test")
        assert svc._receive_task is None

    @pytest.mark.asyncio
    async def test_teardown_closes_websocket(self):
        svc = TransportService()
        mock_ws = AsyncMock()
        svc._ws = mock_ws
        await svc._teardown("test")
        mock_ws.close.assert_called_once()
        assert svc._ws is None

    @pytest.mark.asyncio
    async def test_teardown_handles_ws_close_exception(self):
        svc = TransportService()
        mock_ws = AsyncMock()
        mock_ws.close.side_effect = Exception("already closed")
        svc._ws = mock_ws
        await svc._teardown("test")
        assert svc._ws is None  # Still cleaned up

    @pytest.mark.asyncio
    async def test_teardown_skips_handshake_reset_when_requested(self):
        svc = TransportService()
        svc.handshake.transition_to(HandshakeState.AUTHENTICATING)
        svc.handshake.transition_to(HandshakeState.FAILED)
        await svc._teardown("test", reset_handshake=False)
        assert svc.handshake.state == HandshakeState.FAILED


# ---------------------------------------------------------------------------
# Handle unexpected close
# ---------------------------------------------------------------------------


class TestHandleUnexpectedClose:
    @pytest.mark.asyncio
    async def test_unexpected_close_schedules_reconnect(self):
        svc = TransportService()
        svc._intentional_disconnect = False
        await svc._handle_unexpected_close()
        assert svc._reconnect_task is not None
        svc._cancel_reconnect()

    @pytest.mark.asyncio
    async def test_intentional_disconnect_skips_reconnect(self):
        svc = TransportService()
        svc._intentional_disconnect = True
        await svc._handle_unexpected_close()
        assert svc._reconnect_task is None

    @pytest.mark.asyncio
    async def test_banned_state_skips_reconnect(self):
        svc = TransportService()
        svc.handshake.transition_to(HandshakeState.BANNED)
        await svc._handle_unexpected_close()
        assert svc._reconnect_task is None

    @pytest.mark.asyncio
    async def test_version_outdated_skips_reconnect(self):
        svc = TransportService()
        svc.handshake.transition_to(HandshakeState.VERSION_OUTDATED)
        await svc._handle_unexpected_close()
        assert svc._reconnect_task is None


# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------


class TestKeepalive:
    @pytest.mark.asyncio
    async def test_start_keepalive_creates_task(self):
        svc = TransportService()
        svc._ws = MagicMock()
        svc._start_keepalive()
        assert svc._keepalive_task is not None
        svc._stop_keepalive()

    @pytest.mark.asyncio
    async def test_stop_keepalive_cancels_task(self):
        svc = TransportService()
        svc._ws = MagicMock()
        svc._start_keepalive()
        svc._stop_keepalive()
        assert svc._keepalive_task is None

    @pytest.mark.asyncio
    async def test_double_start_replaces_task(self):
        svc = TransportService()
        svc._ws = MagicMock()
        svc._start_keepalive()
        first_task = svc._keepalive_task
        assert first_task is not None
        svc._start_keepalive()
        assert svc._keepalive_task is not first_task
        await asyncio.sleep(0)  # let cancellation propagate
        assert first_task.cancelled()
        svc._stop_keepalive()


# ---------------------------------------------------------------------------
# Idle timer
# ---------------------------------------------------------------------------


class TestIdleTimer:
    @pytest.mark.asyncio
    async def test_reset_idle_timer_creates_task(self):
        svc = TransportService()
        svc._reset_idle_timer()
        assert svc._idle_timer is not None
        svc._idle_timer.cancel()

    @pytest.mark.asyncio
    async def test_reset_idle_timer_replaces_previous(self):
        svc = TransportService()
        svc._reset_idle_timer()
        first = svc._idle_timer
        assert first is not None
        svc._reset_idle_timer()
        await asyncio.sleep(0)  # let cancellation propagate
        assert first.cancelled()
        if svc._idle_timer is not None:
            svc._idle_timer.cancel()
