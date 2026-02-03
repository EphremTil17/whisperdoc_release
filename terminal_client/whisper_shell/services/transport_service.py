import asyncio
import json
import ssl
import gc
from urllib.parse import urlparse
from loguru import logger
import websockets
import requests
import ipaddress
import socket
from typing import Optional, Callable, Awaitable

from ..services.config_service import cfg, sec_cfg
from ..logic.handshake import HandshakeStateMachine, HandshakeState
from ..logic.payload import PayloadBuilder

class TransportService:
    """
    Service managing WebSocket connectivity and the application-level handshake.
    Enforces the 'No data before Authenticated' security rule.
    """
    def __init__(self):
        self._ws = None
        self._uri = cfg.WS_URI
        self.hostname = urlparse(self._uri).hostname or "localhost"
        self._final_uri = self._prepare_uri(self._uri)
        
        self.handshake = HandshakeStateMachine()
        self._message_listeners = []
        self._receive_task = None
        self._idle_timer = None

    def _reset_idle_timer(self):
        """Resets the idle timer on activity."""
        if self._idle_timer:
            self._idle_timer.cancel()
        
        async def _timeout():
            await asyncio.sleep(cfg.IDLE_TIMEOUT)
            if self._ws:
                logger.info(f"Idle for {cfg.IDLE_TIMEOUT}s. Disconnecting to save server resources.")
                await self.disconnect(reason="Idle Timeout")

        self._idle_timer = asyncio.create_task(_timeout())

    def _prepare_uri(self, uri: str) -> str:
        parsed = urlparse(uri)
        hostname = parsed.hostname or "localhost"
        scheme = parsed.scheme.lower() if parsed.scheme else "ws"
        
        if scheme == "https": scheme = "wss"
        elif scheme == "http": scheme = "ws"
            
        if hostname not in ["localhost", "127.0.0.1", "0.0.0.0"] and scheme == "ws":
            logger.warning("Remote connection detected. Enforcing WSS (TLS/SSL)...")
            scheme = "wss"
        
        path = parsed.path or "/ws"
        final = f"{scheme}://{parsed.netloc}{path}"
        if parsed.query: final += f"?{parsed.query}"
        return final

    async def connect(self) -> bool:
        """Establishes connection and initiates the application-level handshake."""
        if self._ws: return True
        
        logger.info(f"Connecting to {self.hostname}...")
        self.handshake.reset()

        try:
            # 1. Prepare Strict SSL Context
            scheme = urlparse(self._final_uri).scheme
            ssl_context = None
            if scheme == "wss":
                ssl_context = ssl.create_default_context()
                # Zero-Trust Enforcement: Explicitly ensure hostname and cert verification
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                logger.debug(f"TLS Verification Enabled for {self.hostname}")

            self._ws = await websockets.connect(
                self._final_uri, 
                ssl=ssl_context
            )
            
            # Start background receiver
            self._receive_task = asyncio.create_task(self._listen_loop())
            
            # Send Client Hello
            api_key = sec_cfg.get_api_key(self.hostname)
            if not api_key:
                raise Exception("No API Key available for authentication.")
            
            payload = PayloadBuilder.build_hello(
                token=api_key,
                auth_type="api_key",
                incognito=cfg.args.incognito
            )
            
            await self._send_json(payload)
            
            # Immediate Memory Hygiene: Clear sensitive strings from local scope
            del api_key
            del payload
            gc.collect()
            
            self.handshake.transition_to(HandshakeState.AUTHENTICATING)
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self.disconnect(reason=str(e))
            return False

    async def ensure_connected(self) -> bool:
        """Background auto-wake pattern."""
        if self.handshake.state == HandshakeState.AUTHENTICATED:
            return True
        return await self.connect()

    async def _listen_loop(self):
        """Infinite loop for receiving messages."""
        try:
            async for message in self._ws:
                await self._handle_raw_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket closed: {e.code} - {e.reason}")
            await self.disconnect(reason="Closed by server")
        except Exception as e:
            logger.error(f"Transport receiver error: {e}")
            await self.disconnect(reason=str(e))

    async def _handle_raw_message(self, data):
        if not isinstance(data, str): return
        self._reset_idle_timer()

        try:
            msg = json.loads(data)
            event = msg.get("event")

            if event == "hello":
                # Server is ready,HandshakeStateMachine handles transitions 
                # but we've already sent our hello in connect() for speed
                pass
            elif event == "authenticated":
                self.handshake.transition_to(HandshakeState.AUTHENTICATED)
                logger.success(f"Authenticated CID: {msg.get('cid', 'unknown')}")
                # Memory Hygiene: Trigger GC after security-sensitive handshake
                gc.collect()
            elif event == "error":
                code = msg.get("code")
                if code in [401, 403, 1008]:
                    self.handshake.transition_to(HandshakeState.FAILED)
                    if code == 1008: self.handshake.transition_to(HandshakeState.BANNED)
                
                # Notify listeners even on error
                for cb in self._message_listeners: await cb(msg)
            else:
                # Notify all feature-specific listeners (e.g. RecordingController)
                for cb in self._message_listeners: await cb(msg)
                
        except Exception as e:
            logger.error(f"Message parsing error: {e}")

    async def send_audio(self, chunk: bytes):
        """Sends raw PCM chunks ONLY if authenticated."""
        if self.handshake.can_send_audio() and self._ws:
            self._reset_idle_timer()
            await self._ws.send(chunk)
        else:
            # The controller should be buffering if we aren't authenticated yet
            pass

    async def _send_json(self, data: dict):
        if self._ws:
            self._reset_idle_timer()
            await self._ws.send(json.dumps(data))

    async def disconnect(self, reason: str = "Client closed"):
        self.handshake.reset()
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None
            
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None
        
        if self._ws:
            await self._ws.close(1000, reason)
            self._ws = None
        logger.info(f"Disconnected: {reason}")

    def add_message_listener(self, callback: Callable[[dict], Awaitable[None]]):
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
