import asyncio
import gc
import json
import random
import ssl
from typing import cast
from urllib.parse import urlparse

import requests
import websockets
from loguru import logger

from ..logic.handshake import HandshakeState, HandshakeStateMachine
from ..logic.messages import JSONValue, MessageListener, ServerMessage
from ..logic.payload import PayloadBuilder
from ..services.config_service import cfg, sec_cfg

# Cloudflare Tunnel drops idle WebSocket connections after ~100s.
# Ping interval must sit well below that threshold.
KEEPALIVE_INTERVAL_S = 45

# Reconnection backoff parameters
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 60.0
BACKOFF_FACTOR = 2.0
MAX_RECONNECT_ATTEMPTS = 10


class TransportService:
    """
    Service managing WebSocket connectivity, the application-level handshake,
    keepalive pings, and automatic reconnection with exponential backoff.
    """

    def __init__(self):
        self._ws = None
        self._uri = cfg.WS_URI
        self.hostname = urlparse(self._uri).hostname or "localhost"
        self._final_uri = self._prepare_uri(self._uri)

        self.handshake = HandshakeStateMachine()
        self._message_listeners: list[MessageListener] = []
        self._receive_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._idle_timer: asyncio.Task | None = None
        self._reconnect_attempt = 0
        self._reconnect_task: asyncio.Task | None = None
        self._intentional_disconnect = False

    # ------------------------------------------------------------------
    # URI preparation
    # ------------------------------------------------------------------

    def _prepare_uri(self, uri: str) -> str:
        parsed = urlparse(uri)
        hostname = parsed.hostname or "localhost"
        scheme = parsed.scheme.lower() if parsed.scheme else "ws"

        if scheme == "https":
            scheme = "wss"
        elif scheme == "http":
            scheme = "ws"

        if hostname not in ("localhost", "127.0.0.1", "0.0.0.0") and scheme == "ws":
            logger.warning("Remote connection detected. Enforcing WSS (TLS/SSL)...")
            scheme = "wss"

        path = parsed.path or "/ws"
        final = f"{scheme}://{parsed.netloc}{path}"
        if parsed.query:
            final += f"?{parsed.query}"
        return final

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Establishes connection and initiates the application-level handshake."""
        if self._ws:
            return True

        self._intentional_disconnect = False
        self._cancel_reconnect()
        logger.info(f"Connecting to {self.hostname}...")
        self.handshake.reset()

        try:
            scheme = urlparse(self._final_uri).scheme
            ssl_context = None
            if scheme == "wss":
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                logger.debug(f"TLS Verification Enabled for {self.hostname}")

            self._ws = await websockets.connect(
                self._final_uri,
                ssl=ssl_context,
            )

            self._receive_task = asyncio.create_task(self._listen_loop())
            self._start_keepalive()

            api_key = sec_cfg.get_api_key(self.hostname)
            if not api_key:
                raise ValueError("No API Key available for authentication.")

            payload = PayloadBuilder.build_hello(
                token=api_key,
                auth_type="api_key",
                incognito=cfg.args.incognito,
            )
            await self.send_json(payload)

            del api_key
            del payload
            gc.collect()

            self.handshake.transition_to(HandshakeState.AUTHENTICATING)
            self._reconnect_attempt = 0
            return True

        except websockets.exceptions.InvalidStatus as e:
            body = (
                e.response.body.decode(errors="replace")
                if hasattr(e.response, "body") and e.response.body
                else "(no body)"
            )
            logger.error(f"Connection failed: HTTP {e.response.status_code}")
            logger.error(f"Response body: {body}")
            await self._handle_connection_failure()
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self._handle_connection_failure()
            return False

    async def ensure_connected(self) -> bool:
        """Background auto-wake pattern with reconnection guard."""
        if self.handshake.state == HandshakeState.AUTHENTICATED:
            return True
        if self.handshake.state in (
            HandshakeState.BANNED,
            HandshakeState.VERSION_OUTDATED,
        ):
            return False
        return await self.connect()

    async def disconnect(self, reason: str = "Client closed"):
        """Intentional disconnect — cancels all background tasks and resets state."""
        self._intentional_disconnect = True
        await self._teardown(reason)

    # ------------------------------------------------------------------
    # Message receive loop
    # ------------------------------------------------------------------

    async def _listen_loop(self):
        try:
            ws = self._ws
            if ws is None:
                return
            async for message in ws:
                await self._handle_raw_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket closed: {e.code} - {e.reason}")
            await self._handle_unexpected_close()
        except Exception as e:
            logger.error(f"Transport receiver error: {e}")
            await self._handle_unexpected_close()

    async def _handle_raw_message(self, data: object) -> None:
        if not isinstance(data, str):
            return
        self._reset_idle_timer()

        try:
            msg = cast(ServerMessage, json.loads(data))
            event = msg.get("event")

            if event == "hello":
                logger.debug("Server hello acknowledged")
            elif event == "authenticated":
                self.handshake.transition_to(HandshakeState.AUTHENTICATED)
                logger.success(f"Authenticated CID: {msg.get('cid', 'unknown')}")
                gc.collect()
            elif event == "pong":
                logger.debug("Keepalive pong received")
            elif event == "error":
                self._handle_error_message(msg)
            else:
                for cb in self._message_listeners:
                    await cb(msg)

        except Exception as e:
            logger.error(f"Message parsing error: {e}")

    def _handle_error_message(self, msg: ServerMessage) -> None:
        """Routes server error payloads to the appropriate handshake state."""
        error_code = msg.get("error_code", "")
        code = msg.get("code")
        message = msg.get("message", "Unknown error")

        self.handshake.set_error_context(error_code, message)

        if error_code == "IP_BANNED":
            logger.error(f"IP Banned: {message}")
            self.handshake.transition_to(HandshakeState.BANNED)
        elif error_code == "VERSION_OUTDATED":
            logger.error(f"Version outdated: {message}. Please update your client.")
            self.handshake.transition_to(HandshakeState.VERSION_OUTDATED)
        elif error_code == "AUTH_FAILED":
            logger.error(f"Authentication failed: {message}")
            sec_cfg.clear_key(self.hostname)
            self.handshake.transition_to(HandshakeState.FAILED)
        elif error_code == "MAX_CONNECTIONS":
            logger.warning(f"Server at capacity: {message}")
            self.handshake.transition_to(HandshakeState.FAILED)
        elif error_code == "HANDSHAKE_REQUIRED":
            logger.warning(f"Handshake required: {message}")
            self.handshake.transition_to(HandshakeState.FAILED)
        elif error_code in ("MALFORMED_JSON", "INVALID_EVENT", "DUPLICATE_HANDSHAKE"):
            logger.error(f"Protocol error ({error_code}): {message}")
            self.handshake.transition_to(HandshakeState.FAILED)
        elif error_code in ("BUFFER_EXCEEDED", "TRANSCRIPTION_FAILED", "SERVER_ERROR"):
            logger.error(f"Server error ({error_code}): {message}")
            # Operational errors — notify listeners, don't transition handshake
            self._notify_listeners(msg)
            return
        elif error_code == "NO_AUDIO":
            logger.info(f"No audio detected: {message}")
            self._notify_listeners(msg)
            return
        else:
            # Fallback for legacy payloads without error_code
            if code in (401, 403, 1008):
                logger.error(f"Server error (code={code}): {message}")
                self.handshake.transition_to(HandshakeState.FAILED)
            else:
                logger.warning(f"Unrecognized error: {msg}")
                self._notify_listeners(msg)
                return

        # Notify listeners for terminal errors too
        self._notify_listeners(msg)

    # ------------------------------------------------------------------
    # Send methods
    # ------------------------------------------------------------------

    async def send_audio(self, chunk: bytes):
        """Sends raw PCM chunks ONLY if authenticated."""
        if self.handshake.can_send_audio() and self._ws:
            self._reset_idle_timer()
            await self._ws.send(chunk)

    async def send_json(self, data: dict[str, JSONValue]) -> None:
        if self._ws:
            self._reset_idle_timer()
            await self._ws.send(json.dumps(data))

    def _notify_listeners(self, msg: ServerMessage) -> None:
        """Dispatches async listeners in runtime code and sync-style tests."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            for cb in self._message_listeners:
                asyncio.run(cb(msg))
            return

        for cb in self._message_listeners:
            loop.create_task(cb(msg))

    # ------------------------------------------------------------------
    # Keepalive ping
    # ------------------------------------------------------------------

    def _start_keepalive(self):
        self._stop_keepalive()

        async def _ping_loop():
            while self._ws:
                await asyncio.sleep(KEEPALIVE_INTERVAL_S)
                if self._ws and self.handshake.state == HandshakeState.AUTHENTICATED:
                    try:
                        await self.send_json({"event": "ping"})
                        logger.debug("Keepalive ping sent")
                    except Exception:
                        break

        self._keepalive_task = asyncio.create_task(_ping_loop())

    def _stop_keepalive(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    # ------------------------------------------------------------------
    # Idle timer
    # ------------------------------------------------------------------

    def _reset_idle_timer(self):
        if self._idle_timer:
            self._idle_timer.cancel()

        async def _timeout():
            await asyncio.sleep(cfg.IDLE_TIMEOUT)
            if self._ws:
                logger.info(
                    f"Idle for {cfg.IDLE_TIMEOUT}s. Disconnecting to save server resources."
                )
                await self.disconnect(reason="Idle Timeout")

        self._idle_timer = asyncio.create_task(_timeout())

    # ------------------------------------------------------------------
    # Reconnection with exponential backoff + jitter
    # ------------------------------------------------------------------

    async def _handle_connection_failure(self):
        """Called after a failed connect() — tears down partial state and schedules retry."""
        await self._teardown("Connection failed", reset_handshake=False)
        self._schedule_reconnect()

    async def _handle_unexpected_close(self):
        """Called when the server closes the connection unexpectedly."""
        # Terminal states should not trigger reconnection
        if self.handshake.state in (
            HandshakeState.BANNED,
            HandshakeState.VERSION_OUTDATED,
        ):
            await self._teardown("Terminal error")
            return

        await self._teardown("Closed by server", reset_handshake=False)

        if not self._intentional_disconnect:
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_attempt >= MAX_RECONNECT_ATTEMPTS:
            logger.error(
                f"Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) reached. "
                "Use hotkey to retry manually."
            )
            self._reconnect_attempt = 0
            return

        delay = min(
            BACKOFF_BASE_S * (BACKOFF_FACTOR**self._reconnect_attempt), BACKOFF_MAX_S
        )
        jitter = random.uniform(0, delay * 0.3)
        wait = delay + jitter
        self._reconnect_attempt += 1

        logger.info(
            f"Reconnecting in {wait:.1f}s (attempt {self._reconnect_attempt}/{MAX_RECONNECT_ATTEMPTS})..."
        )

        async def _reconnect():
            await asyncio.sleep(wait)
            await self.connect()

        self._reconnect_task = asyncio.create_task(_reconnect())

    def _cancel_reconnect(self):
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

    # ------------------------------------------------------------------
    # Teardown / cleanup
    # ------------------------------------------------------------------

    async def _teardown(self, reason: str, reset_handshake: bool = True):
        """Cancels background tasks and closes the socket."""
        self._stop_keepalive()

        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None

        if self._ws:
            try:
                await self._ws.close(1000, reason)
            except Exception as e:
                logger.debug(f"Ignoring socket-close error during teardown: {e}")
            self._ws = None

        if reset_handshake:
            self.handshake.reset()

        logger.info(f"Disconnected: {reason}")

    # ------------------------------------------------------------------
    # Listeners & health check
    # ------------------------------------------------------------------

    def add_message_listener(self, callback: MessageListener) -> None:
        self._message_listeners.append(callback)

    def check_health(self) -> bool:
        """Pre-flight health check (HTTP)."""
        parsed = urlparse(self._final_uri)
        scheme = "https" if parsed.scheme == "wss" else "http"
        health_url = f"{scheme}://{parsed.netloc}/health"

        logger.info(f"Health Check: {health_url}...")
        try:
            resp = requests.get(health_url, timeout=5)
            if resp.status_code == 200:
                logger.success("Server is healthy.")
                return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
        return False
