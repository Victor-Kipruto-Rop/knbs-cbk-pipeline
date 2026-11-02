import datetime as dt
import io
import openpyxl
import pytest
from knbs_cbk_pipeline.transformation.cleaners.knbs_cleaner import clean_gdp

def test_gdp_cleaner_parses_quarterly_workbook():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Quarter", "GDP at market prices"])
    sheet.append(["Q1 2025", 345678.2])
    sheet.append(["Q2 2025", 351234.5])
    buffer = io.BytesIO()
    workbook.save(buffer)
    rows = clean_gdp(buffer.getvalue(), dt.datetime(2025, 8, 1, tzinfo=dt.timezone.utc))
    assert len(rows) == 2
    assert rows.iloc[0]["period_date"] == "2025-01-01"
    assert rows.iloc[1]["indicator_code"] == "knbs_gdp_quarterly"

def test_gdp_cleaner_fails_closed_on_unknown_layout():
    workbook = openpyxl.Workbook()
    workbook.active.append(["Fiscal year", "Some unrelated statistic"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    with pytest.raises(ValueError, match="no recognizable"):
        clean_gdp(buffer.getvalue(), dt.datetime.now(dt.timezone.utc))
