"""Warehouse table definitions shared by the loader and dbt source models."""
from __future__ import annotations
from sqlalchemy import Column, Date, DateTime, Float, Index, MetaData, String, Table, UniqueConstraint

metadata = MetaData()

economic_indicators = Table(
    "economic_indicators", metadata,
    Column("id", String, primary_key=True),
    Column("indicator_code", String, nullable=False),
    Column("indicator_name", String, nullable=False),
    Column("period_date", Date, nullable=False),
    Column("value", Float, nullable=False),
    Column("unit", String, nullable=False),
    Column("source_id", String, nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("indicator_code", "period_date", "source_id", name="uq_indicator_period_source"),
)

economic_indicator_versions = Table(
    "economic_indicator_versions", metadata,
    Column("version_id", String, primary_key=True),
    Column("indicator_code", String, nullable=False),
    Column("indicator_name", String, nullable=False),
    Column("period_date", Date, nullable=False),
    Column("value", Float, nullable=False),
    Column("previous_value", Float, nullable=True),
    Column("unit", String, nullable=False),
    Column("source_id", String, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)
Index(
    "ix_indicator_versions_natural_key",
    economic_indicator_versions.c.indicator_code,
    economic_indicator_versions.c.period_date,
    economic_indicator_versions.c.source_id,
)
