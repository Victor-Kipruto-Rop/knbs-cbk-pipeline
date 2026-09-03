from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

from os import getenv

CURSOR_TTL_SECONDS = int(getenv("KCP_CURSOR_TTL", str(60 * 60 * 24 * 7)))  # default 7 days
CURSOR_SECRET = getenv("KCP_CURSOR_SECRET", "change-me")


def _sign(message: bytes) -> str:
    sig = hmac.new(CURSOR_SECRET.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode()


def encode_cursor(payload: Dict[str, Any], ttl: Optional[int] = None) -> str:
    """Encode and sign a cursor payload. Adds `exp` (epoch seconds).

    Returned format: base64url(json).<sig>
    """
    now = int(time.time())
    expires = now + (ttl if ttl is not None else CURSOR_TTL_SECONDS)
    payload_copy = dict(payload)
    payload_copy.setdefault("exp", expires)
    raw = json.dumps(payload_copy, separators=(",", ":"), sort_keys=True).encode()
    b64 = base64.urlsafe_b64encode(raw).decode()
    sig = _sign(raw)
    return f"{b64}.{sig}"


class InvalidCursor(Exception):
    pass


def decode_cursor(cursor: str) -> Dict[str, Any]:
    """Verify signature and expiry, return decoded payload or raise InvalidCursor."""
    try:
        b64, sig = cursor.rsplit(".", 1)
    except ValueError:
        raise InvalidCursor("bad format")
    try:
        raw = base64.urlsafe_b64decode(b64.encode())
        expected_sig = _sign(raw)
        if not hmac.compare_digest(expected_sig, sig):
            raise InvalidCursor("bad signature")
        payload = json.loads(raw.decode())
        exp = int(payload.get("exp", 0))
        # treat expiry as inclusive to avoid edge cases with integer seconds
        if exp and int(time.time()) >= exp:
            raise InvalidCursor("expired")
        return payload
    except (ValueError, json.JSONDecodeError) as e:
        raise InvalidCursor(str(e))
