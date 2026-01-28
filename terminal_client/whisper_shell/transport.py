import asyncio
import json
import time
import sys
from urllib.parse import urlparse
from loguru import logger
import websockets
import requests
import ipaddress
import socket
from .config import cfg, SecureConfig

class TransportManager:
    def __init__(self):
        self.ws = None
        self.uri = cfg.WS_URI
        self.hostname = urlparse(self.uri).hostname or "localhost"
        self._prepare_uri()

    def _prepare_uri(self):
        """
        Parses URI and normalizes protocols. 
        Enforces WSS for remote hosts, tolerates WS for local development.
        """
        parsed = urlparse(self.uri)
        hostname = parsed.hostname or "localhost"
        scheme = parsed.scheme.lower() if parsed.scheme else "ws"
        
        # 1. Base Normalization: Convert HTTP -> WS
        if scheme == "https":
            scheme = "wss"
        elif scheme == "http":
            scheme = "ws"
            
        # 2. Security Enforcement: Upgrade to WSS for remote hosts unless already WSS
        if hostname not in ["localhost", "127.0.0.1", "0.0.0.0"]:
            if scheme == "ws":
                logger.warning("Remote connection detected. Upgrading to WSS (TLS/SSL)...")
                scheme = "wss"
        
        # 3. Path Normalization: Ensure /ws is present if not specified
        path = parsed.path
        if not path or path == "/":
            path = "/ws"
            
        self.final_uri = f"{scheme}://{parsed.netloc}{path}"
        if parsed.query: 
            self.final_uri += f"?{parsed.query}"
            
        logger.info(f"Target Server: {self.final_uri}")

    def check_health(self):
        """Performs a Pre-flight Health Check."""
        # Convert WS/WSS -> HTTP/HTTPS
        parsed = urlparse(self.final_uri)
        scheme = "https" if parsed.scheme == "wss" else "http"
        health_url = f"{scheme}://{parsed.netloc}/health"
        
        logger.info(f"Checking Server Health: {health_url}...")
        try:
            resp = requests.get(health_url, timeout=5, verify=False) 
        except requests.exceptions.SSLError:
             # Fallback logic for private IPs
             is_private = False
             try:
                 ip = socket.gethostbyname(parsed.hostname)
                 if ipaddress.ip_address(ip).is_private: is_private = True
             except Exception: 
                 pass
             
             if is_private:
                  logger.warning(f"HTTPS failed. Falling back to HTTP for private IP ({ip})...")
                  health_url = health_url.replace("https://", "http://")
                  try:
                      resp = requests.get(health_url, timeout=5)
                  except: return False
             else:
                  logger.error(f"SSL Error on Public IP. Aborting.")
                  return False
        except Exception as e:
            logger.error(f"Health Check Error: {e}")
            return False

        if resp.status_code == 200:
            logger.success("Server is online and healthy.")
            return True
        logger.error(f"Server returned status {resp.status_code}")
        return False

    async def connect(self):
        """Establishes authenticated WebSocket connection."""
        if self.ws: return
        
        # We no longer append the token to the URL to keep logs clean
        connect_uri = self.final_uri
        
        try:
            logger.info(f"Connecting to {self.hostname}...")
            self.ws = await websockets.connect(connect_uri)
        except Exception as e:
            # WSS -> WS Fallback for Private IPs
            is_private = False
            try:
                 ip = socket.gethostbyname(self.hostname)
                 if ipaddress.ip_address(ip).is_private: is_private = True
            except: pass

            if "WRONG_VERSION_NUMBER" in str(e) and is_private:
                logger.warning(f"WSS failed. Falling back to WS for private IP ({ip})...")
                fallback_uri = connect_uri.replace("wss://", "ws://")
                self.ws = await websockets.connect(fallback_uri)
            else:
                raise e

        # Server Handshake (TWO-WAY)
        hello_raw = await self.ws.recv()
        hello = json.loads(hello_raw)
        
        if hello.get("event") == "hello":
             # Send Client Hello with token
             api_key = SecureConfig.get_api_key(self.hostname)
             
             await self.ws.send(json.dumps({
                 "event": "hello",
                 "client": "whisper_shell",
                 "version": cfg.VERSION,
                 "token": api_key,
                 "incognito": cfg.args.incognito
             }))
             
             # Wait for Auth Verification
             try:
                 auth_raw = await asyncio.wait_for(self.ws.recv(), timeout=10.0)
                 auth_resp = json.loads(auth_raw)
                 
                 if auth_resp.get("event") == "authenticated":
                      logger.success(f"Connected to {self.hostname} (v{hello.get('version')})")
                 elif auth_resp.get("event") == "error":
                      raise Exception(f"Auth Failed: {auth_resp.get('message')}")
                 else:
                      raise Exception("Handshake failed: Invalid response from server.")
             except asyncio.TimeoutError:
                 raise Exception("Handshake timeout: Server response delayed.")
        else:
             logger.warning("Protocol mismatch: No hello received.")

    async def send(self, data):
        if self.ws: await self.ws.send(data)

    async def recv(self):
        if self.ws: return await self.ws.recv()
        return None

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
