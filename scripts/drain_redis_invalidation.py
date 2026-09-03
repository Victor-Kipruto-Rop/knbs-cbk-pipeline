"""Drain tracked Redis cache keys in batches to avoid long blocking deletes.

Usage:
  python scripts/drain_redis_invalidation.py --prefix indicators:cache: --limit 500
"""
from __future__ import annotations

import argparse
import time
import logging

from knbs_cbk_pipeline.api.cache import delete_prefix_limited, get_redis

logger = logging.getLogger("drain_invalidation")
logging.basicConfig(level=logging.INFO)


def drain(prefix: str, limit: int, interval: float) -> None:
    r = get_redis()
    if not r:
        logger.error("Redis not available (KCP_REDIS_URL not configured)")
        return

    total_deleted = 0
    while True:
        deleted, remaining = delete_prefix_limited(prefix, limit)
        total_deleted += deleted
        logger.info("batch_deleted", deleted=deleted, remaining=remaining, total_deleted=total_deleted)
        if remaining == 0:
            logger.info("drain_complete", total_deleted=total_deleted)
            break
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=str, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between batches")
    args = parser.parse_args()
    drain(args.prefix, args.limit, args.interval)


if __name__ == "__main__":
    main()
