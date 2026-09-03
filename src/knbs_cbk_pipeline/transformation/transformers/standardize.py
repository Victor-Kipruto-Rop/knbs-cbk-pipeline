"""
Final normalization pass before data is loaded to staging: consistent
dtypes, rounding, and a de-dup safety net. Cleaners focus on parsing;
this module focuses on making every source's output byte-for-byte
consistent in shape.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd


def standardize(df: pd.DataFrame, *, ingested_at: dt.datetime | None = None) -> pd.DataFrame:
    out = df.copy()

    out["period_date"] = pd.to_datetime(out["period_date"]).dt.date.astype(str)
    out["value"] = out["value"].astype(float).round(4)
    out["indicator_code"] = out["indicator_code"].str.strip().str.lower()
    out["source_id"] = out["source_id"].str.strip().str.lower()
    out["ingested_at"] = (ingested_at or dt.datetime.now(dt.timezone.utc)).isoformat()

    # Safety net: cleaners already dedupe within a run, but if the same
    # period is re-ingested (e.g. a manual backfill overlapping a scheduled
    # run) keep the latest ingested row per natural key.
    out = out.sort_values("ingested_at").drop_duplicates(
        subset=["indicator_code", "period_date", "source_id"], keep="last"
    )
    return out.reset_index(drop=True)
