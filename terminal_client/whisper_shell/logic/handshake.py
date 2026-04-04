import asyncio
from enum import Enum, auto
from typing import Callable

from loguru import logger


class HandshakeState(Enum):
    LOCKED = auto()  # Initial state, no handshake initiated
    AUTHENTICATING = auto()  # Sent hello, waiting for authenticated response
    AUTHENTICATED = auto()  # Handshake complete, can send audio
    FAILED = auto()  # Authentication failed or timeout
    BANNED = auto()  # IP banned by server
    VERSION_OUTDATED = auto()  # Client version rejected by server


class HandshakeStateMachine:
    def __init__(self, timeout: float = 15.0):
        self._state = HandshakeState.LOCKED
        self._timeout_duration = timeout
        self._timeout_task: asyncio.Task[None] | None = None
        self._listeners: list[Callable[[HandshakeState], object]] = []
        self._last_error_code: str | None = None
        self._last_message: str | None = None
        self._listener_tasks: set[asyncio.Task[object]] = set()

    @property
    def state(self) -> HandshakeState:
        return self._state

    @property
    def last_error_code(self) -> str | None:
        return self._last_error_code

    @property
    def last_message(self) -> str | None:
        return self._last_message

    def set_error_context(self, error_code: str | None, message: str | None) -> None:
        self._last_error_code = error_code
        self._last_message = message

    def transition_to(self, new_state: HandshakeState) -> None:
        if self._state == new_state:
            return

        if not self._is_valid_transition(self._state, new_state):
            logger.warning(
                f"Invalid state transition: {self._state.name} -> {new_state.name}"
            )
            return

        logger.info(f"Handshake state: {self._state.name} -> {new_state.name}")
        self._state = new_state

        for listener in self._listeners:
            if asyncio.iscoroutinefunction(listener):
                task = asyncio.create_task(listener(new_state))
                self._listener_tasks.add(task)
                task.add_done_callback(self._listener_tasks.discard)
            else:
                listener(new_state)

        if new_state == HandshakeState.AUTHENTICATING:
            self._start_timeout()
        else:
            self._cancel_timeout()

    def can_send_audio(self) -> bool:
        return self._state == HandshakeState.AUTHENTICATED

    def reset(self) -> None:
        self._cancel_timeout()
        self._last_error_code = None
        self._last_message = None
        self.transition_to(HandshakeState.LOCKED)

    def _is_valid_transition(
        self, from_state: HandshakeState, to_state: HandshakeState
    ) -> bool:
        # Terminal error states reachable from any active state
        if to_state in (HandshakeState.BANNED, HandshakeState.VERSION_OUTDATED):
            return True

        valid = {
            HandshakeState.LOCKED: {
                HandshakeState.AUTHENTICATING,
                HandshakeState.FAILED,
            },
            HandshakeState.AUTHENTICATING: {
                HandshakeState.AUTHENTICATED,
                HandshakeState.FAILED,
            },
            HandshakeState.AUTHENTICATED: {
                HandshakeState.LOCKED,
            },
            HandshakeState.FAILED: {
                HandshakeState.LOCKED,
            },
            HandshakeState.BANNED: {
                HandshakeState.LOCKED,
            },
            HandshakeState.VERSION_OUTDATED: {
                HandshakeState.LOCKED,
            },
        }
        return to_state in valid.get(from_state, set())

    def _start_timeout(self) -> None:
        self._cancel_timeout()

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # No running event loop (e.g. unit tests)

        async def _timeout_coro():
            await asyncio.sleep(self._timeout_duration)
            if self._state == HandshakeState.AUTHENTICATING:
                logger.warning(
                    f"Handshake timeout: No response from server after {self._timeout_duration}s"
                )
                self.set_error_context(None, "Handshake timed out")
                self.transition_to(HandshakeState.FAILED)

        self._timeout_task = asyncio.create_task(_timeout_coro())

    def _cancel_timeout(self) -> None:
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

    def add_listener(self, callback: Callable[[HandshakeState], object]) -> None:
        self._listeners.append(callback)
