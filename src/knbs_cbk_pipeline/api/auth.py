from __future__ import annotations

import os
import time
from fastapi import Header, HTTPException, Response
from typing import Optional

from knbs_cbk_pipeline.api.cache import get_redis


def get_api_key(response: Response, x_api_key: Optional[str] = Header(None)) -> Optional[str]:
    """Validate API key if enforcement is enabled via KCP_REQUIRE_API_KEY.

    Also perform a simple Redis-backed rate limit per key.
    """
    require = os.getenv("KCP_REQUIRE_API_KEY", "false").lower() in ("1", "true", "yes")
    if not require:
        return None

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")

    allowed = os.getenv("KCP_API_KEYS", "").split(",")
    allowed = [k.strip() for k in allowed if k.strip()]
    if x_api_key not in allowed:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # rate limit: default 300 requests per minute
    rate_limit = int(os.getenv("KCP_RATE_LIMIT", "300"))
    redis = get_redis()
    cur = None
    reset = None
    if redis:
        try:
            window = int(time.time() // 60)
            key = f"ratelimit:{x_api_key}:{window}"
            cur = redis.incr(key)
            if cur == 1:
                redis.expire(key, 65)
            reset = (window + 1) * 60 - int(time.time())
            if cur > rate_limit:
                # set headers before raising
                response.headers["X-RateLimit-Limit"] = str(rate_limit)
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(reset)
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        except HTTPException:
            raise
        except Exception:
            # on Redis errors, fail open but still attempt to set best-effort headers
            cur = None

    # provide rate-limit headers even when Redis not configured
    remaining = rate_limit - cur if (cur is not None) else rate_limit
    if remaining < 0:
        remaining = 0
    response.headers.setdefault("X-RateLimit-Limit", str(rate_limit))
    response.headers.setdefault("X-RateLimit-Remaining", str(remaining))
    response.headers.setdefault("X-RateLimit-Reset", str(reset if reset is not None else 60))

    return x_api_key
