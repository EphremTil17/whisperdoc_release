from enum import Enum, auto
import asyncio
from loguru import logger

class HandshakeState(Enum):
    LOCKED = auto()          # Initial state, no handshake initiated
    AUTHENTICATING = auto() # Sent hello, waiting for authenticated response
    AUTHENTICATED = auto()  # Handshake complete, can send audio
    FAILED = auto()         # Authentication failed or timeout
    BANNED = auto()         # IP banned by server (1008 close code)

class HandshakeStateMachine:
    def __init__(self, timeout=15):
        self._state = HandshakeState.LOCKED
        self._timeout_duration = timeout
        self._timeout_task = None
        self._listeners = []

    @property
    def state(self):
        return self._state

    def transition_to(self, new_state: HandshakeState):
        if self._state == new_state:
            return

        if not self._is_valid_transition(self._state, new_state):
            logger.warning(f"Invalid state transition: {self._state.name} -> {new_state.name}")
            return

        logger.info(f"Handshake state: {self._state.name} -> {new_state.name}")
        self._state = new_state
        
        # Notify listeners
        for listener in self._listeners:
            if asyncio.iscoroutinefunction(listener):
                asyncio.create_task(listener(new_state))
            else:
                listener(new_state)

        # Handle timeout
        if new_state == HandshakeState.AUTHENTICATING:
            self._start_timeout()
        else:
            self._cancel_timeout()

    def can_send_audio(self) -> bool:
        return self._state == HandshakeState.AUTHENTICATED

    def reset(self):
        self._cancel_timeout()
        self.transition_to(HandshakeState.LOCKED)

    def _is_valid_transition(self, from_state: HandshakeState, to_state: HandshakeState) -> bool:
        if to_state == HandshakeState.BANNED:
            return True

        if from_state == HandshakeState.LOCKED:
            return to_state in [HandshakeState.AUTHENTICATING, HandshakeState.FAILED]
        
        if from_state == HandshakeState.AUTHENTICATING:
            return to_state in [HandshakeState.AUTHENTICATED, HandshakeState.FAILED]
        
        if from_state == HandshakeState.AUTHENTICATED:
            return to_state == HandshakeState.LOCKED
        
        if from_state == HandshakeState.FAILED:
            return to_state == HandshakeState.LOCKED
            
        if from_state == HandshakeState.BANNED:
            return to_state == HandshakeState.LOCKED

        return False

    def _start_timeout(self):
        self._cancel_timeout()
        async def _timeout_coro():
            await asyncio.sleep(self._timeout_duration)
            if self._state == HandshakeState.AUTHENTICATING:
                logger.warning(f"Handshake timeout: No response from server after {self._timeout_duration}s")
                self.transition_to(HandshakeState.FAILED)
        
        self._timeout_task = asyncio.create_task(_timeout_coro())

    def _cancel_timeout(self):
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

    def add_listener(self, callback):
        self._listeners.append(callback)
