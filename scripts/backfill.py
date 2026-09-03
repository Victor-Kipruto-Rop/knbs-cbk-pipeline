"""
Reprocesses already-landed raw files through transformation without
re-fetching from source. Use when a cleaner bug is fixed and history needs
correcting, or when validators were tightened after the fact.

Usage:
    python scripts/backfill.py --source-id knbs_cpi
    python scripts/backfill.py --all
"""
from __future__ import annotations

import argparse

import structlog

from knbs_cbk_pipeline.transformation.runner import transform_and_load_all

log = structlog.get_logger()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", action="append", help="Repeatable; omit with --all for every source")
    parser.add_argument("--all", action="store_true", help="Reprocess every registered source")
    args = parser.parse_args()

    if not args.all and not args.source_id:
        parser.error("pass --source-id at least once, or --all")

    source_ids = None if args.all else args.source_id
    results = transform_and_load_all(source_ids=source_ids)

    for source_id, count in results.items():
        status = "FAILED" if count < 0 else f"{count} rows"
        log.info("backfill.result", source_id=source_id, status=status)


if __name__ == "__main__":
    main()
