"""
Core table definitions, shared between the Postgres loader and dbt's
`source()` declarations (see dbt/models/staging/_sources.yml — table and
column names must match exactly).

No explicit schema= is set on MetaData: in Postgres, point the connection's
search_path at "staging" (see docker-compose / postgres init SQL); this
keeps the table definition portable enough to also run against SQLite in
tests, which doesn't support multi-schema DDL the same way.
"""
from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, Float, MetaData, String, Table, UniqueConstraint

metadata = MetaData()

economic_indicators = Table(
    "economic_indicators",
    metadata,
    Column("id", String, primary_key=True),  # deterministic hash of the natural key
    Column("indicator_code", String, nullable=False),
    Column("indicator_name", String, nullable=False),
    Column("period_date", Date, nullable=False),
    Column("value", Float, nullable=False),
    Column("unit", String, nullable=False),
    Column("source_id", String, nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("indicator_code", "period_date", "source_id", name="uq_indicator_period_source"),
)
