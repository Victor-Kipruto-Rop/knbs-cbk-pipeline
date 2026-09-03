from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

REDIS_URL = os.getenv("KCP_REDIS_URL")

_redis = None
if REDIS_URL:
    try:
        import redis

        _redis = redis.from_url(REDIS_URL)
    except Exception:
        _redis = None


def compute_etag(items: Any, meta: Any) -> str:
    payload = json.dumps({"meta": meta, "items": items}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def cache_get(key: str) -> Optional[str]:
    if not _redis:
        return None
    try:
        return _redis.get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl: int = 300) -> None:
    if not _redis:
        return
    try:
        _redis.set(key, value, ex=ttl)
        try:
            # track cache keys for efficient invalidation
            _redis.sadd("indicators:keys", key)
        except Exception:
            pass
    except Exception:
        return


def delete_prefix(prefix: str) -> int:
    """Delete keys matching prefix. Returns number of deleted keys."""
    if not _redis:
        return 0
    try:
        # Try to use a Lua script for atomic, fast deletion using the tracked set.
        lua = """
        local members = redis.call('SMEMBERS', 'indicators:keys')
        local p = ARGV[1]
        local count = 0
        for i=1,#members do
            local k = members[i]
            if string.sub(k,1,string.len(p)) == p then
                redis.call('DEL', k)
                redis.call('SREM', 'indicators:keys', k)
                count = count + 1
            end
        end
        return count
        """
        try:
            # redis-py eval signature: eval(script, numkeys, *keys_and_args)
            res = _redis.eval(lua, 0, prefix)
            if isinstance(res, int):
                return res
        except Exception:
            # fall back to Python set-scan deletion if eval not allowed
            pass

        count = 0
        # Use the tracked set for deterministic deletion of known cache keys
        members = _redis.smembers("indicators:keys") or set()
        for k in list(members):
            try:
                # redis returns bytes; normalize
                if isinstance(k, bytes):
                    ks = k.decode()
                else:
                    ks = k
                if ks.startswith(prefix):
                    _redis.delete(ks)
                    _redis.srem("indicators:keys", ks)
                    count += 1
            except Exception:
                continue
        return count
    except Exception:
        return 0


def delete_prefix_limited(prefix: str, limit: int) -> tuple[int, int]:
    """Delete up to `limit` keys matching prefix. Returns (deleted_count, remaining_count).

    Uses a Lua script to perform deletions server-side for efficiency.
    """
    if not _redis:
        return (0, 0)
    try:
        lua = """
        local members = redis.call('SMEMBERS', 'indicators:keys')
        local p = ARGV[1]
        local lim = tonumber(ARGV[2])
        local deleted = 0
        local remaining = 0
        for i=1,#members do
            local k = members[i]
            if string.sub(k,1,string.len(p)) == p then
                if deleted < lim then
                    redis.call('DEL', k)
                    redis.call('SREM', 'indicators:keys', k)
                    deleted = deleted + 1
                else
                    remaining = remaining + 1
                end
            end
        end
        return {deleted, remaining}
        """
        try:
            res = _redis.eval(lua, 0, prefix, limit)
            # redis-py may return a list of integers
            if isinstance(res, (list, tuple)) and len(res) == 2:
                return (int(res[0]), int(res[1]))
        except Exception:
            pass

        # fallback to non-atomic python loop (should rarely be used)
        deleted = 0
        remaining = 0
        members = _redis.smembers("indicators:keys") or set()
        for k in list(members):
            try:
                if isinstance(k, bytes):
                    ks = k.decode()
                else:
                    ks = k
                if ks.startswith(prefix):
                    if deleted < limit:
                        _redis.delete(ks)
                        _redis.srem("indicators:keys", ks)
                        deleted += 1
                    else:
                        remaining += 1
            except Exception:
                continue
        return (deleted, remaining)
    except Exception:
        return (0, 0)


def make_cache_key(filters: dict, cursor: Optional[str], page_size: int, fmt: str) -> str:
    """Create a deterministic cache key for a query given filters, cursor, page_size and format."""
    key_obj = {"f": filters or {}, "c": cursor, "ps": page_size, "fmt": fmt}
    payload = json.dumps(key_obj, sort_keys=True, default=str)
    return "indicators:cache:" + hashlib.sha256(payload.encode()).hexdigest()


def get_redis():
    return _redis
