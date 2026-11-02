"""Idempotent current-state upserts plus append-only observation revision history."""
from __future__ import annotations
import hashlib
import pandas as pd
import structlog
from sqlalchemy import Engine, create_engine, select, and_
from sqlalchemy.dialects import postgresql, sqlite
from config.settings import settings
from knbs_cbk_pipeline.warehouse.tables import economic_indicators, economic_indicator_versions, metadata
log = structlog.get_logger()

def _natural_key_id(row: pd.Series) -> str:
    raw = f"{row['indicator_code']}|{row['period_date']}|{row['source_id']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _version_id(row: dict) -> str:
    raw = "|".join(str(row[k]) for k in (
        "indicator_code", "period_date", "source_id", "value", "unit", "ingested_at"
    ))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def get_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or settings.database_url, pool_pre_ping=True)

def ensure_schema(engine: Engine) -> None:
    metadata.create_all(engine)

def upsert_indicators(df: pd.DataFrame, engine: Engine) -> int:
    """Upsert current observations and preserve each distinct revision exactly once."""
    if df.empty:
        return 0
    records = df.copy()
    records["id"] = records.apply(_natural_key_id, axis=1)
    records["period_date"] = pd.to_datetime(records["period_date"]).dt.date
    records["ingested_at"] = pd.to_datetime(records["ingested_at"], utc=True)
    rows = records.to_dict(orient="records")

    dialect_name = engine.dialect.name
    if dialect_name == "postgresql":
        insert_fn = postgresql.insert
    elif dialect_name == "sqlite":
        insert_fn = sqlite.insert
    else:
        raise NotImplementedError(f"No upsert strategy for dialect '{dialect_name}'")

    with engine.begin() as conn:
        revisions = []
        for row in rows:
            current = conn.execute(
                select(
                    economic_indicators.c.indicator_name,
                    economic_indicators.c.value,
                    economic_indicators.c.unit,
                ).where(and_(
                    economic_indicators.c.indicator_code == row["indicator_code"],
                    economic_indicators.c.period_date == row["period_date"],
                    economic_indicators.c.source_id == row["source_id"],
                ))
            ).mappings().first()
            changed = current is None or (
                current["indicator_name"] != row["indicator_name"]
                or float(current["value"]) != float(row["value"])
                or current["unit"] != row["unit"]
            )
            if changed:
                revision = {
                    "version_id": _version_id(row),
                    "indicator_code": row["indicator_code"],
                    "indicator_name": row["indicator_name"],
                    "period_date": row["period_date"],
                    "value": row["value"],
                    "previous_value": float(current["value"]) if current else None,
                    "unit": row["unit"],
                    "source_id": row["source_id"],
                    "recorded_at": row["ingested_at"],
                }
                revisions.append(revision)

        if revisions:
            version_stmt = insert_fn(economic_indicator_versions).values(revisions)
            version_stmt = version_stmt.on_conflict_do_nothing(index_elements=["version_id"])
            conn.execute(version_stmt)

        stmt = insert_fn(economic_indicators).values(rows)
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in ("indicator_name", "value", "unit", "ingested_at")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["indicator_code", "period_date", "source_id"],
            set_=update_cols,
            where=stmt.excluded.ingested_at >= economic_indicators.c.ingested_at,
        )
        conn.execute(stmt)

    log.info("loader.upserted", rows=len(rows), revisions=len(revisions), dialect=dialect_name)
    try:
        from knbs_cbk_pipeline.api.cache import delete_prefix_limited
        delete_prefix_limited("indicators:etag:", 500)
        delete_prefix_limited("indicators:cache:", 500)
    except Exception:
        log.exception("loader.cache_invalidation_failed")
    return len(rows)
