from knbs_cbk_pipeline.api.utils.cursors import encode_cursor, decode_cursor, InvalidCursor
import time


def test_encode_decode_cursor():
    payload = {"period_date": "2026-09-03", "indicator_code": "abc", "ingested_at": "2026-09-03T12:00:00"}
    cur = encode_cursor(payload, ttl=2)
    decoded = decode_cursor(cur)
    assert decoded["period_date"] == payload["period_date"]
    assert decoded["indicator_code"] == payload["indicator_code"]


def test_expired_cursor():
    payload = {"period_date": "2026-09-03", "indicator_code": "abc"}
    cur = encode_cursor(payload, ttl=1)
    time.sleep(1.25)
    try:
        decode_cursor(cur)
        assert False, "expected InvalidCursor"
    except InvalidCursor:
        pass
