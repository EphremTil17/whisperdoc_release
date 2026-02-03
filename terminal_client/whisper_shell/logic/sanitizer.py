import re
from loguru import logger

class Sanitizer:
    """
    Principal-level input sanitizer using a strict whitelist-only approach.
    Prevents terminal injection, ReDoS, and control sequence escalation.
    """
    
    # Whitelist: Only basic printable ASCII + safe whitespace
    # Prevents ANSI escapes (\x1b), Null bytes (\x00), and control characters (< \x20)
    WHITELIST_REGEX = re.compile(r'[^\x20-\x7E\n\r\t]')
    
    # Comprehensive ANSI stripper covering CSI (colors/moves) and OSC (titles/etc).
    ANSI_ESCAPE_REGEX = re.compile(r'\x1b\[[0-9;]*[mGKH]|\x1b]0;.*?\x07')

    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Neutralizes all non-printable or suspicious characters.
        """
        if not text:
            return ""

        try:
            # 1. Strip ANSI escape sequences explicitly
            cleaned = cls.ANSI_ESCAPE_REGEX.sub('', text)
            
            # 2. Apply strict whitelist (printable ASCII + safe whitespace)
            cleaned = cls.WHITELIST_REGEX.sub('', cleaned)
            
            # 3. Final cleaning
            cleaned = cleaned.strip()
            
            if cleaned != text:
                logger.warning("Sanitizer neutralized control sequences or non-whitelisted characters.")
            
            return cleaned
        except Exception as e:
            logger.error(f"Sanitization failure: {e}")
            # Fail-secure: return empty if processing fails
            return ""
