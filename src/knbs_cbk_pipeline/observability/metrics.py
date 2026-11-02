"""Operational health metrics with source-specific freshness SLAs."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
import structlog
import yaml
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

def _source_slas() -> dict[str, int]:
    try:
        with settings.sources_config_path.open(encoding="utf-8") as handle:
            sources = (yaml.safe_load(handle) or {}).get("sources", [])
        return {
            source["id"]: int(source.get("freshness_sla_hours", settings.freshness_sla_hours))
            for source in sources
        }
    except (OSError, ValueError, TypeError, KeyError):
        log.exception("metrics.source_registry_unavailable")
        return {}

def freshness_by_source(engine: Engine) -> list[SourceHealth]:
    recent_runs = read_recent_runs(limit=500)
    last_run_by_source: dict[str, dict] = {}
    for run in recent_runs:
        last_run_by_source[run["source_id"]] = run

    with engine.connect() as conn:
        rows = conn.execute(select(
            economic_indicators.c.source_id,
            func.count().label("row_count"),
            func.max(economic_indicators.c.period_date).label("latest_period_date"),
        ).group_by(economic_indicators.c.source_id)).fetchall()

    warehouse_by_source = {row.source_id: row for row in rows}
    slas = _source_slas()
    all_source_ids = set(slas) | set(last_run_by_source) | set(warehouse_by_source)
    results = []
    for source_id in sorted(all_source_ids):
        run, wh = last_run_by_source.get(source_id), warehouse_by_source.get(source_id)
        latest_period = wh.latest_period_date.isoformat() if wh and wh.latest_period_date else None
        sla = slas.get(source_id, settings.freshness_sla_hours)
        results.append(SourceHealth(
            source_id=source_id,
            last_run_success=run["success"] if run else None,
            last_run_at=run["finished_at"] if run else None,
            row_count=wh.row_count if wh else 0,
            latest_period_date=latest_period,
            is_stale=_is_stale(latest_period, sla),
        ))
    return results

def _is_stale(latest_period_date: str | None, sla_hours: int) -> bool:
    if latest_period_date is None:
        return True
    period = dt.date.fromisoformat(latest_period_date)
    age_hours = (dt.datetime.now(dt.timezone.utc).date() - period).days * 24
    return age_hours > sla_hours
