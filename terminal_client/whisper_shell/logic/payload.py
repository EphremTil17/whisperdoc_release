from typing import Dict
from ..services.config_service import cfg

class PayloadBuilder:
    """
    Standardizes WebSocket payloads to match backend expectations.
    """
    @staticmethod
    def build_hello(token: str, auth_type: str = "api_key", incognito: bool = False) -> Dict:
        """
        Constructs the mandatory application-level handshake payload.
        Including 'auth_type' triggers user-specific model hot-reloading on the backend.
        """
        return {
            "event": "hello",
            "client": "whisper.client.terminal",
            "version": "2.20.0", # Hardcoded or from config
            "auth_type": auth_type,
            "token": token,
            "incognito": incognito
        }

    @staticmethod
    def build_end_of_stream() -> Dict:
        return {"event": "end-of-stream"}
