"""CBK feed parsers producing a shared tidy observation schema."""
from __future__ import annotations
import datetime as dt
import json
import re
import pandas as pd
from bs4 import BeautifulSoup

TIDY_COLUMNS = ["indicator_code", "indicator_name", "period_date", "value", "unit", "source_id"]
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
_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|[A-Za-z]{3,9}\s*,?\s*\d{4})\b")

def clean_fx_rates(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    payload = json.loads(raw_bytes)
    base, period_date = payload["base"], payload["date"]
    rows = [{
        "indicator_code": f"cbk_fx_{base.lower()}_{ccy.lower()}",
        "indicator_name": f"{base}/{ccy} indicative exchange rate",
        "period_date": period_date, "value": float(rate),
        "unit": f"{ccy} per {base}", "source_id": "cbk_fx_rates",
    } for ccy, rate in payload["rates"].items()]
    return pd.DataFrame(rows, columns=TIDY_COLUMNS)

def _row_period(row_text: str, fetched_at: dt.datetime) -> str:
    match = _DATE_RE.search(row_text)
    if match:
        raw = match.group(1).replace(",", " ")
        try:
            return pd.to_datetime(raw, dayfirst=True, errors="raise").date().isoformat()
        except (ValueError, TypeError):
            pass
    return fetched_at.date().isoformat()

def clean_key_rates(raw_bytes: bytes, fetched_at: dt.datetime) -> pd.DataFrame:
    soup = BeautifulSoup(raw_bytes, "lxml")
    text_rows = [tr.get_text(" ", strip=True) for tr in soup.find_all("tr")]
    rows = []
    for row_text in text_rows:
        for label, (code, unit) in _KEY_RATE_LABELS.items():
            if row_text.startswith(label):
                match = _PERCENT_RE.search(row_text)
                if not match:
                    continue
                rows.append({
                    "indicator_code": code, "indicator_name": label,
                    "period_date": _row_period(row_text, fetched_at),
                    "value": float(match.group(1)), "unit": unit, "source_id": "cbk_key_rates",
                })
                break
    return pd.DataFrame(rows, columns=TIDY_COLUMNS)
