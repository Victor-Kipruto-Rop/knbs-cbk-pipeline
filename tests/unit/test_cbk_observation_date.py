import datetime as dt
from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import clean_key_rates

def test_key_rates_use_published_observation_date_when_present():
    html = b'<table><tr><td>Central Bank Rate</td><td>13.00%</td><td>05/06/2024</td></tr></table>'
    rows = clean_key_rates(html, dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc))
    assert rows.iloc[0]["period_date"] == "2024-06-05"
