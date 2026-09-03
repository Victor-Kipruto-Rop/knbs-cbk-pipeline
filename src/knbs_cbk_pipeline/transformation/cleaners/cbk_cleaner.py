"""
Parses raw CBK payloads into the pipeline's shared tidy schema:

    indicator_code | indicator_name | period_date | value | unit | source_id

Every cleaner across every source (CBK, KNBS) targets this same shape —
that's what lets warehouse/models/marts/fct_economic_indicators.sql be a
single fact table instead of one table per source.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd
from bs4 import BeautifulSoup

TIDY_COLUMNS = ["indicator_code", "indicator_name", "period_date", "value", "unit", "source_id"]

# CBK homepage widget label -> (indicator_code, unit). Kept as an explicit
# map (not inferred) so a wording change on the page fails loudly via
# schema_checks rather than silently mis-tagging an indicator.
_KEY_RATE_LABELS = {
    "Central Bank Rate": ("cbk_central_bank_rate", "percent"),
    "Inter-Bank Rate": ("cbk_interbank_rate", "percent"),
    "CBK Discount Window": ("cbk_discount_window", "percent"),
    "91-Day T-Bill": ("cbk_91day_tbill", "percent"),
    "REPO": ("cbk_repo_rate", "percent"),
    "Inflation Rate": ("cbk_inflation_rate", "percent"),
    "Lending Rate": ("cbk_lending_rate", "percent"),
    "Savings Rate": ("cbk_savings_rate", "percent"),
    "Deposit Rate": ("cbk_deposit_rate", "percent"),
    "KBRR": ("cbk_kbrr", "percent"),
}

_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def clean_fx_rates(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    """cbk_fx_rates: Frankfurter/CBK JSON -> one row per currency pair."""
    payload = json.loads(raw_bytes)
    base = payload["base"]
    period_date = payload["date"]

    rows = [
        {
            "indicator_code": f"cbk_fx_{base.lower()}_{ccy.lower()}",
            "indicator_name": f"{base}/{ccy} indicative exchange rate",
            "period_date": period_date,
            "value": rate,
            "unit": f"{ccy} per {base}",
            "source_id": "cbk_fx_rates",
        }
        for ccy, rate in payload["rates"].items()
    ]
    return pd.DataFrame(rows, columns=TIDY_COLUMNS)


def clean_key_rates(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    """cbk_key_rates: CBK homepage widget HTML -> one row per policy rate."""
    soup = BeautifulSoup(raw_bytes, "lxml")
    text_rows = [tr.get_text(" ", strip=True) for tr in soup.find_all("tr")]

    rows = []
    for row_text in text_rows:
        for label, (code, unit) in _KEY_RATE_LABELS.items():
            if row_text.startswith(label):
                match = _PERCENT_RE.search(row_text)
                if not match:
                    continue
                rows.append(
                    {
                        "indicator_code": code,
                        "indicator_name": label,
                        # The widget's "as-of" date is unreliable across
                        # rows (mix of dd/mm/yyyy and "Month,YYYY"); use the
                        # fetch date as the period marker and let the value
                        # itself carry whatever CBK most recently published.
                        "period_date": fetched_at.date().isoformat(),
                        "value": float(match.group(1)),
                        "unit": unit,
                        "source_id": "cbk_key_rates",
                    }
                )
                break

    return pd.DataFrame(rows, columns=TIDY_COLUMNS)
