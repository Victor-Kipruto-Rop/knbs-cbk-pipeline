"""Tests freshness/alerting logic against an in-memory warehouse."""
import datetime as dt

import pandas as pd
from sqlalchemy import create_engine

from knbs_cbk_pipeline.observability.alerts import check_and_alert
from knbs_cbk_pipeline.observability.metrics import freshness_by_source
from knbs_cbk_pipeline.observability.run_metadata import RunRecord, record_run
from knbs_cbk_pipeline.transformation.transformers.standardize import standardize
from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import ensure_schema, upsert_indicators


def test_fresh_source_reports_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "knbs_cbk_pipeline.observability.run_metadata.RUN_LOG_PATH",
        tmp_path / "_run_metadata.jsonl",
    )
    engine = create_engine("sqlite:///:memory:")
    ensure_schema(engine)

    today = dt.datetime.now(dt.timezone.utc)
    df = pd.DataFrame(
        [
            {
                "indicator_code": "cbk_fx_usd_kes",
                "indicator_name": "USD/KES",
                "period_date": today.date().isoformat(),
                "value": 129.0,
                "unit": "KES per USD",
                "source_id": "cbk_fx_rates",
            }
        ]
    )
    upsert_indicators(standardize(df, ingested_at=today), engine)
    record_run(RunRecord.mark_success("cbk_fx_rates", raw_path=tmp_path / "f.json", byte_size=10))

    health = freshness_by_source(engine)
    cbk_health = next(h for h in health if h.source_id == "cbk_fx_rates")

    assert cbk_health.last_run_success is True
    assert cbk_health.is_stale is False
    assert cbk_health.row_count == 1

    alerts = check_and_alert(health)
    assert alerts == []  # nothing wrong -> no alerts


def test_stale_and_failed_source_triggers_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "knbs_cbk_pipeline.observability.run_metadata.RUN_LOG_PATH",
        tmp_path / "_run_metadata.jsonl",
    )
    engine = create_engine("sqlite:///:memory:")
    ensure_schema(engine)

    old_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).date().isoformat()
    df = pd.DataFrame(
        [
            {
                "indicator_code": "knbs_cpi_index",
                "indicator_name": "CPI",
                "period_date": old_date,
                "value": 140.0,
                "unit": "index",
                "source_id": "knbs_cpi",
            }
        ]
    )
    upsert_indicators(standardize(df), engine)
    record_run(RunRecord.mark_failure("knbs_cpi", error="upstream 404"))

    health = freshness_by_source(engine)
    alerts = check_and_alert(health)

    assert any("FAILED" in a for a in alerts)
    assert any("stale" in a for a in alerts)
