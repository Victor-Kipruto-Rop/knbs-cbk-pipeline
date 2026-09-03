"""
Loads a standardized tidy DataFrame into the staging.economic_indicators
table via an idempotent upsert keyed on (indicator_code, period_date,
source_id) — reruns of the same day's ingestion never create duplicates.

Dialect-aware (`postgresql` vs `sqlite` insert) so the same code path is
exercised in tests (SQLite) and production (Postgres) rather than testing
a mock of the load logic.
"""
from __future__ import annotations

import datetime as dt
import hashlib

import pandas as pd
import structlog
from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects import postgresql, sqlite

from config.settings import settings
from knbs_cbk_pipeline.warehouse.tables import economic_indicators, metadata
from knbs_cbk_pipeline.api.cache import cache_set

log = structlog.get_logger()


def _natural_key_id(row: pd.Series) -> str:
    raw = f"{row['indicator_code']}|{row['period_date']}|{row['source_id']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def get_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or settings.database_url)


def ensure_schema(engine: Engine) -> None:
    metadata.create_all(engine)


def upsert_indicators(df: pd.DataFrame, engine: Engine) -> int:
    """Upsert a standardized tidy DataFrame. Returns the number of rows written."""
    if df.empty:
        return 0

    records = df.copy()
    records["id"] = records.apply(_natural_key_id, axis=1)
    # SQLAlchemy's Date type requires actual date objects, not ISO strings,
    # across dialects (SQLite enforces this strictly; Postgres/psycopg2 is
    # lenient but we keep one code path for both).
    records["period_date"] = pd.to_datetime(records["period_date"]).dt.date
    records["ingested_at"] = pd.to_datetime(records["ingested_at"])
    rows = records.to_dict(orient="records")

    dialect_name = engine.dialect.name
    if dialect_name == "postgresql":
        insert_fn = postgresql.insert
    elif dialect_name == "sqlite":
        insert_fn = sqlite.insert
    else:
        raise NotImplementedError(f"No upsert strategy for dialect '{dialect_name}'")

    stmt = insert_fn(economic_indicators).values(rows)
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in ("indicator_name", "value", "unit", "ingested_at")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["indicator_code", "period_date", "source_id"],
        set_=update_cols,
    )

    with engine.begin() as conn:
        conn.execute(stmt)

    log.info("loader.upserted", rows=len(rows), dialect=dialect_name)
    # invalidate caches related to indicators after upsert
    try:
        # delete cached query results and etag entries in limited batches
        from knbs_cbk_pipeline.api.cache import delete_prefix_limited

        # delete up to 500 keys per call to avoid long blocking deletes
        delete_prefix_limited("indicators:etag:", 500)
        delete_prefix_limited("indicators:cache:", 500)
    except Exception:
        pass
    return len(rows)
