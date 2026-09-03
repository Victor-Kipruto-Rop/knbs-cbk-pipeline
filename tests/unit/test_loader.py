"""
Tests the standardize -> upsert chain against an in-memory SQLite DB.
Proves the loader's upsert logic (dedup on natural key, update-on-conflict)
using the same code path production Postgres uses, just a different dialect.
"""
import datetime as dt

import pandas as pd
from sqlalchemy import create_engine, select

from knbs_cbk_pipeline.transformation.transformers.standardize import standardize
from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import ensure_schema, upsert_indicators
from knbs_cbk_pipeline.warehouse.tables import economic_indicators


def _sample_df(value: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "indicator_code": "cbk_fx_usd_kes",
                "indicator_name": "USD/KES indicative exchange rate",
                "period_date": "2026-09-02",
                "value": value,
                "unit": "KES per USD",
                "source_id": "cbk_fx_rates",
            }
        ]
    )


def test_upsert_inserts_then_updates_on_rerun():
    engine = create_engine("sqlite:///:memory:")
    ensure_schema(engine)

    fixed_time = dt.datetime(2026, 9, 3, 6, 0, tzinfo=dt.timezone.utc)

    # first run
    df1 = standardize(_sample_df(129.31), ingested_at=fixed_time)
    written = upsert_indicators(df1, engine)
    assert written == 1

    with engine.connect() as conn:
        rows = conn.execute(select(economic_indicators)).fetchall()
    assert len(rows) == 1
    assert rows[0].value == 129.31

    # second run, same day, corrected value -> should UPDATE not duplicate
    later = fixed_time + dt.timedelta(hours=1)
    df2 = standardize(_sample_df(129.40), ingested_at=later)
    upsert_indicators(df2, engine)

    with engine.connect() as conn:
        rows = conn.execute(select(economic_indicators)).fetchall()
    assert len(rows) == 1, "rerun with same natural key must update, not duplicate"
    assert rows[0].value == 129.40


def test_standardize_drops_intra_batch_duplicates_keeping_latest():
    df = pd.concat([_sample_df(100.0), _sample_df(200.0)], ignore_index=True)
    out = standardize(df, ingested_at=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc))
    assert len(out) == 1
    assert out.iloc[0]["value"] == 200.0
