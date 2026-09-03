"""Unit tests for cleaners + validators against known-shape fixtures."""
import datetime as dt
import io

import openpyxl
import pandas as pd

from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import clean_fx_rates, clean_key_rates
from knbs_cbk_pipeline.transformation.cleaners.knbs_cleaner import clean_cpi
from knbs_cbk_pipeline.transformation.validators.schema_checks import validate_tidy_frame

FETCHED_AT = dt.datetime(2026, 9, 3, 6, 0, tzinfo=dt.timezone.utc)


def test_clean_fx_rates_produces_tidy_rows():
    raw = b'{"amount": 1.0, "base": "USD", "date": "2026-09-02", "rates": {"KES": 129.31, "EUR": 0.92}}'
    df = clean_fx_rates(raw, FETCHED_AT)

    assert len(df) == 2
    kes_row = df[df["indicator_code"] == "cbk_fx_usd_kes"].iloc[0]
    assert kes_row["value"] == 129.31
    assert kes_row["period_date"] == "2026-09-02"

    result = validate_tidy_frame(df, source_id="cbk_fx_rates")
    assert result.ok, result.errors


def test_clean_key_rates_extracts_known_indicators():
    html = b"""
    <table>
      <tr><td>Central Bank Rate</td><td>13.00%</td><td>05/06/2024</td></tr>
      <tr><td>Inflation Rate</td><td>5.1%</td><td>May,2024</td></tr>
      <tr><td>Some Unrelated Row</td><td>n/a</td></tr>
    </table>
    """
    df = clean_key_rates(html, FETCHED_AT)

    assert len(df) == 2
    codes = set(df["indicator_code"])
    assert codes == {"cbk_central_bank_rate", "cbk_inflation_rate"}

    result = validate_tidy_frame(df, source_id="cbk_key_rates")
    assert result.ok, result.errors


def test_clean_cpi_parses_synthetic_workbook():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Month", "CPI", "Annual Inflation"])
    ws.append(["2026-07-01", 145.2, 5.3])
    ws.append(["2026-08-01", 146.0, 5.6])
    buf = io.BytesIO()
    wb.save(buf)

    df = clean_cpi(buf.getvalue(), FETCHED_AT)

    assert len(df) == 4  # 2 months x (cpi + inflation)
    cpi_rows = df[df["indicator_code"] == "knbs_cpi_index"]
    assert len(cpi_rows) == 2
    assert cpi_rows.iloc[0]["value"] == 145.2

    result = validate_tidy_frame(df, source_id="knbs_cpi")
    assert result.ok, result.errors


def test_validator_catches_empty_frame():
    empty = pd.DataFrame(columns=["indicator_code", "indicator_name", "period_date", "value", "unit", "source_id"])
    result = validate_tidy_frame(empty, source_id="cbk_fx_rates")
    assert not result.ok
    assert "zero rows" in result.errors[0]


def test_validator_catches_duplicate_natural_key():
    df = pd.DataFrame(
        [
            {"indicator_code": "x", "indicator_name": "X", "period_date": "2026-09-01", "value": 1.0, "unit": "percent", "source_id": "s"},
            {"indicator_code": "x", "indicator_name": "X", "period_date": "2026-09-01", "value": 2.0, "unit": "percent", "source_id": "s"},
        ]
    )
    result = validate_tidy_frame(df, source_id="s")
    assert not result.ok
    assert any("duplicate" in e for e in result.errors)
