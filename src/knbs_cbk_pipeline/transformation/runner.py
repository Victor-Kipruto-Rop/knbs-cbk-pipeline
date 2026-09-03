"""
Second pipeline stage: reads raw files landed by ingestion/runner.py,
routes each to its cleaner by source_id, validates, standardizes, and
upserts into staging.economic_indicators.

Mirrors ingestion/runner.py's shape deliberately — same "registry lookup,
try/except per item, record outcome" pattern, so a maintainer who
understands one stage understands both.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable

import pandas as pd
import structlog
from sqlalchemy import Engine

from config.settings import settings
from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import clean_fx_rates, clean_key_rates
from knbs_cbk_pipeline.transformation.cleaners.knbs_cleaner import clean_cpi
from knbs_cbk_pipeline.transformation.transformers.standardize import standardize
from knbs_cbk_pipeline.transformation.validators.schema_checks import validate_tidy_frame
from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import ensure_schema, get_engine, upsert_indicators

log = structlog.get_logger()

CleanerFn = Callable[[bytes, dt.datetime], pd.DataFrame]

_CLEANERS: dict[str, CleanerFn] = {
    "cbk_fx_rates": clean_fx_rates,
    "cbk_key_rates": clean_key_rates,
    "knbs_cpi": clean_cpi,
}


def _latest_raw_file(source_id: str, raw_dir: Path) -> Path | None:
    candidates = [
        p for p in (raw_dir / source_id).rglob("*") if p.is_file() and not p.name.endswith(".meta.json")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def transform_and_load_source(source_id: str, engine: Engine, raw_dir: Path | None = None) -> int:
    """Clean, validate, standardize, and load the latest raw file for one source."""
    raw_dir = raw_dir or settings.raw_data_dir
    cleaner = _CLEANERS.get(source_id)
    if cleaner is None:
        raise ValueError(f"No cleaner registered for source_id '{source_id}'")

    raw_file = _latest_raw_file(source_id, raw_dir)
    if raw_file is None:
        log.warning("transform.no_raw_file", source_id=source_id)
        return 0

    fetched_at = dt.datetime.fromtimestamp(raw_file.stat().st_mtime, tz=dt.timezone.utc)
    tidy = cleaner(raw_file.read_bytes(), fetched_at)

    result = validate_tidy_frame(tidy, source_id=source_id)
    if result.warnings:
        log.warning("transform.validation_warnings", source_id=source_id, warnings=result.warnings)
    result.raise_if_invalid()  # hard failure on real data quality problems

    clean_df = standardize(tidy)
    written = upsert_indicators(clean_df, engine)
    log.info("transform.loaded", source_id=source_id, rows=written)
    return written


def transform_and_load_all(source_ids: list[str] | None = None, engine: Engine | None = None) -> dict[str, int]:
    engine = engine or get_engine()
    ensure_schema(engine)

    ids = source_ids or list(_CLEANERS.keys())
    results: dict[str, int] = {}
    for source_id in ids:
        try:
            results[source_id] = transform_and_load_source(source_id, engine)
        except Exception as exc:  # noqa: BLE001 - one bad source shouldn't kill the run
            log.error("transform.failed", source_id=source_id, error=str(exc))
            results[source_id] = -1
    return results


if __name__ == "__main__":
    transform_and_load_all()
