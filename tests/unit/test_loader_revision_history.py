import datetime as dt
import pandas as pd
from sqlalchemy import create_engine, select
from knbs_cbk_pipeline.transformation.transformers.standardize import standardize
from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import ensure_schema, upsert_indicators
from knbs_cbk_pipeline.warehouse.tables import economic_indicators, economic_indicator_versions

def _row(value):
    return pd.DataFrame([{
        "indicator_code": "cbk_fx_usd_kes",
        "indicator_name": "USD/KES indicative exchange rate",
        "period_date": "2026-09-02",
        "value": value,
        "unit": "KES per USD",
        "source_id": "cbk_fx_rates",
    }])

def test_revisions_are_recorded_once_and_old_replay_cannot_regress_current_value():
    engine = create_engine("sqlite:///:memory:")
    ensure_schema(engine)
    first = dt.datetime(2026, 9, 3, 6, 0, tzinfo=dt.timezone.utc)
    second = first + dt.timedelta(hours=1)
    upsert_indicators(standardize(_row(129.31), ingested_at=first), engine)
    upsert_indicators(standardize(_row(129.40), ingested_at=second), engine)
    upsert_indicators(standardize(_row(129.31), ingested_at=first), engine)

    with engine.connect() as conn:
        current = conn.execute(select(economic_indicators)).mappings().all()
        versions = conn.execute(select(economic_indicator_versions)).mappings().all()
    assert len(current) == 1
    assert current[0]["value"] == 129.40
    assert len(versions) == 2
    corrected = next(v for v in versions if v["value"] == 129.40)
    assert corrected["previous_value"] == 129.31
