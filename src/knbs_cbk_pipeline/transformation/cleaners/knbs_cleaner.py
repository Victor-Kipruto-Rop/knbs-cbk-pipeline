"""Defensive KNBS CPI and quarterly GDP workbook parsers."""
from __future__ import annotations

import datetime as dt
import io
import re

import pandas as pd

from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import TIDY_COLUMNS

_MONTH_COL_CANDIDATES = ["month", "period", "date", "time"]
_CPI_COL_CANDIDATES = ["consumer price index", "cpi index", "cpi"]
_INFLATION_COL_CANDIDATES = ["annual inflation", "inflation rate", "inflation"]


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {c: re.sub(r"[^a-z0-9]+", " ", c.strip().lower()).strip() for c in columns}
    for candidate in candidates:
        for col, label in normalized.items():
            if label == candidate:
                return col
    for candidate in candidates:
        for col, label in normalized.items():
            if candidate in label:
                return col
    return None


def clean_cpi(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    """Convert a CPI workbook into monthly CPI and annual-inflation observations."""
    df = pd.read_excel(io.BytesIO(raw_bytes))
    df.columns = [str(c).strip() for c in df.columns]
    month_col = _find_column(list(df.columns), _MONTH_COL_CANDIDATES)
    cpi_col = _find_column(list(df.columns), _CPI_COL_CANDIDATES)
    inflation_col = _find_column(list(df.columns), _INFLATION_COL_CANDIDATES)
    if month_col is None or (cpi_col is None and inflation_col is None):
        raise ValueError(f"knbs_cpi: unable to identify period and CPI/inflation columns: {list(df.columns)}")

    rows = []
    for _, row in df.iterrows():
        period_date = _coerce_period(row.get(month_col))
        if not period_date:
            continue
        for col, code, name, unit in (
            (cpi_col, "knbs_cpi_index", "Consumer Price Index", "index (base year = 100)"),
            (inflation_col, "knbs_inflation_rate_annual", "Annual inflation rate", "percent"),
        ):
            if col and pd.notna(row.get(col)):
                value = pd.to_numeric(row[col], errors="coerce")
                if pd.notna(value):
                    rows.append({
                        "indicator_code": code, "indicator_name": name, "period_date": period_date,
                        "value": float(value), "unit": unit, "source_id": "knbs_cpi",
                    })
    return pd.DataFrame(rows, columns=TIDY_COLUMNS)


def clean_gdp(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    """Parse quarterly GDP observations from a KNBS Excel release.

    This parser intentionally requires recognizable quarter/period and GDP value
    columns. It fails closed rather than silently mapping an unrelated column.
    """
    workbook = pd.ExcelFile(io.BytesIO(raw_bytes))
    frames = []
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet, header=None)
        if frame.empty:
            continue
        for header_row in range(min(12, len(frame))):
            candidate = frame.iloc[header_row:].copy()
            candidate.columns = [str(v).strip() for v in frame.iloc[header_row].tolist()]
            candidate = candidate.iloc[1:].reset_index(drop=True)
            candidate.columns = [str(c).strip() for c in candidate.columns]
            period_col = _find_column(list(candidate.columns), ["quarter", "period", "year"])
            value_col = _find_column(list(candidate.columns), [
                "gdp at market prices", "gross domestic product", "real gdp", "gdp"
            ])
            if period_col and value_col and value_col != period_col:
                for _, row in candidate.iterrows():
                    period = _coerce_quarter(row.get(period_col))
                    value = pd.to_numeric(row.get(value_col), errors="coerce")
                    if period and pd.notna(value):
                        frames.append({
                            "indicator_code": "knbs_gdp_quarterly",
                            "indicator_name": "Gross domestic product",
                            "period_date": period,
                            "value": float(value),
                            "unit": "KES million (verify against bulletin metadata)",
                            "source_id": "knbs_gdp_quarterly",
                        })
                if frames:
                    break
        if frames:
            break
    if not frames:
        raise ValueError(
            "knbs_gdp_quarterly: no recognizable quarterly period/GDP columns found. "
            "Inspect the workbook layout before changing parser mappings."
        )
    return pd.DataFrame(frames, columns=TIDY_COLUMNS)


def _coerce_period(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return pd.Timestamp(value).date().replace(day=1).isoformat()
    try:
        parsed = pd.to_datetime(str(value), errors="raise")
        return parsed.date().replace(day=1).isoformat()
    except (ValueError, TypeError):
        return None


def _coerce_quarter(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    match = re.search(r"(?:Q|QUARTER\s*)([1-4])\D*(20\d{2})|(20\d{2})\D*(?:Q|QUARTER\s*)([1-4])", text)
    if match:
        quarter = int(match.group(1) or match.group(4))
        year = int(match.group(2) or match.group(3))
        month = (quarter - 1) * 3 + 1
        return f"{year:04d}-{month:02d}-01"
    try:
        parsed = pd.to_datetime(text, errors="raise")
        return f"{parsed.year:04d}-{((parsed.month - 1) // 3) * 3 + 1:02d}-01"
    except (ValueError, TypeError):
        return None
