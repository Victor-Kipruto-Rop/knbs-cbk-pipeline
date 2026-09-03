"""
Parses raw KNBS Excel bulletins into the same tidy schema used by
transformation/cleaners/cbk_cleaner.py.

KNBS bulletin layouts drift release to release (extra footnote rows, merged
header cells, renamed columns) far more than CBK's feeds. This cleaner is
deliberately defensive: it locates columns by fuzzy name match rather than
fixed position, and schema_checks.py is what catches it loudly when a
release changes shape enough that nothing matches.
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd

from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import TIDY_COLUMNS

_MONTH_COL_CANDIDATES = ["month", "period", "date"]
_CPI_COL_CANDIDATES = ["cpi", "consumer price index", "index"]
_INFLATION_COL_CANDIDATES = ["annual inflation", "inflation rate", "inflation"]


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    lowered = {c: c.strip().lower() for c in columns}
    for col, low in lowered.items():
        if any(candidate in low for candidate in candidates):
            return col
    return None


def clean_cpi(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    """knbs_cpi: monthly CPI/inflation Excel bulletin -> tidy rows."""
    df = pd.read_excel(io.BytesIO(raw_bytes))
    df.columns = [str(c).strip() for c in df.columns]

    month_col = _find_column(list(df.columns), _MONTH_COL_CANDIDATES)
    cpi_col = _find_column(list(df.columns), _CPI_COL_CANDIDATES)
    inflation_col = _find_column(list(df.columns), _INFLATION_COL_CANDIDATES)

    if month_col is None:
        raise ValueError(
            "knbs_cpi: could not locate a month/period column — "
            f"available columns were {list(df.columns)}. Bulletin layout "
            "likely changed; update _MONTH_COL_CANDIDATES."
        )

    rows = []
    for _, row in df.iterrows():
        period_raw = row.get(month_col)
        if pd.isna(period_raw):
            continue
        period_date = _coerce_period(period_raw)
        if period_date is None:
            continue

        if cpi_col and pd.notna(row.get(cpi_col)):
            rows.append(
                {
                    "indicator_code": "knbs_cpi_index",
                    "indicator_name": "Consumer Price Index",
                    "period_date": period_date,
                    "value": float(row[cpi_col]),
                    "unit": "index (base year = 100)",
                    "source_id": "knbs_cpi",
                }
            )
        if inflation_col and pd.notna(row.get(inflation_col)):
            rows.append(
                {
                    "indicator_code": "knbs_inflation_rate_annual",
                    "indicator_name": "Annual inflation rate",
                    "period_date": period_date,
                    "value": float(row[inflation_col]),
                    "unit": "percent",
                    "source_id": "knbs_cpi",
                }
            )

    return pd.DataFrame(rows, columns=TIDY_COLUMNS)


def _coerce_period(value: object) -> str | None:
    """Best-effort coercion of KNBS's inconsistent month formats to ISO date."""
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return pd.Timestamp(value).date().isoformat()
    try:
        return pd.to_datetime(str(value), errors="raise").date().isoformat()
    except (ValueError, TypeError):
        return None
