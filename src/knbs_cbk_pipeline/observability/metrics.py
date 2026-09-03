"""
Derives operational metrics from the run-metadata log and the warehouse
itself. This is what a dashboard or a scheduled health-check task reads —
kept separate from alerts.py so metrics can be inspected without
necessarily firing a notification.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import structlog
from sqlalchemy import Engine, func, select

from config.settings import settings
from knbs_cbk_pipeline.observability.run_metadata import read_recent_runs
from knbs_cbk_pipeline.warehouse.tables import economic_indicators

log = structlog.get_logger()


@dataclass
class SourceHealth:
    source_id: str
    last_run_success: bool | None
    last_run_at: str | None
    row_count: int
    latest_period_date: str | None
    is_stale: bool


def freshness_by_source(engine: Engine) -> list[SourceHealth]:
    """One row per source_id: last run outcome + how fresh the warehouse data is."""
    recent_runs = read_recent_runs(limit=500)
    last_run_by_source: dict[str, dict] = {}
    for run in recent_runs:
        last_run_by_source[run["source_id"]] = run  # later entries overwrite -> latest wins

    results = []
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                economic_indicators.c.source_id,
                func.count().label("row_count"),
                func.max(economic_indicators.c.period_date).label("latest_period_date"),
            ).group_by(economic_indicators.c.source_id)
        ).fetchall()

    warehouse_by_source = {r.source_id: r for r in rows}
    all_source_ids = set(last_run_by_source) | set(warehouse_by_source)

    for source_id in sorted(all_source_ids):
        run = last_run_by_source.get(source_id)
        wh = warehouse_by_source.get(source_id)

        latest_period = wh.latest_period_date.isoformat() if wh and wh.latest_period_date else None
        is_stale = _is_stale(latest_period, settings.freshness_sla_hours)

        results.append(
            SourceHealth(
                source_id=source_id,
                last_run_success=run["success"] if run else None,
                last_run_at=run["finished_at"] if run else None,
                row_count=wh.row_count if wh else 0,
                latest_period_date=latest_period,
                is_stale=is_stale,
            )
        )
    return results


def _is_stale(latest_period_date: str | None, sla_hours: int) -> bool:
    if latest_period_date is None:
        return True
    period = dt.date.fromisoformat(latest_period_date)
    age_hours = (dt.datetime.now(dt.timezone.utc).date() - period).days * 24
    return age_hours > sla_hours
