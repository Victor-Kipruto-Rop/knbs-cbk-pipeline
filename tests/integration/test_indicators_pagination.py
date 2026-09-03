from fastapi.testclient import TestClient
from knbs_cbk_pipeline.api.app import app
import knbs_cbk_pipeline.api.routers.indicators as indicators_mod


class FakeResult:
    def __init__(self, rows=None, total=0):
        self._rows = rows or []
        self._total = total

    def first(self):
        return (self._total,)

    def mappings(self):
        class M:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return M(self._rows)


class FakeConnection:
    def __init__(self, rows, total):
        self.rows = rows
        self.total = total

    def execute(self, sql, params=None):
        # simplistic: return total for count query else rows
        text = str(sql).lower()
        if text.strip().startswith("select count"):
            return FakeResult([], total=self.total)
        return FakeResult(rows=self.rows, total=self.total)


class FakeEngine:
    def __init__(self, rows, total):
        self._rows = rows
        self._total = total

    def connect(self):
        class Ctx:
            def __init__(self, rows, total):
                self._conn = FakeConnection(rows, total)

            def __enter__(self):
                return self._conn

            def __exit__(self, exc_type, exc, tb):
                return False

        return Ctx(self._rows, self._total)


def test_pagination_and_link_header(monkeypatch):
    # two pages of data simulated
    rows_page = [
        {"indicator_code": "a", "indicator_name": "A", "period_date": "2026-09-03", "value": 1, "unit": "u", "source_id": "s", "ingested_at": "2026-09-03T12:00:00"},
        {"indicator_code": "b", "indicator_name": "B", "period_date": "2026-09-03", "value": 2, "unit": "u", "source_id": "s", "ingested_at": "2026-09-03T12:01:00"},
    ]
    total = 4
    fake = FakeEngine(rows_page, total)
    monkeypatch.setattr(indicators_mod, "get_engine", lambda: fake)

    client = TestClient(app)
    resp = client.get("/indicators/top?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total"] == total
    assert len(data["items"]) == 2
    assert "link" in resp.headers or "Link" in resp.headers
