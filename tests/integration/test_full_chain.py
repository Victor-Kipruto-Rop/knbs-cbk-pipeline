"""
Full chain: mocked HTTP -> ingestion.runner (raw landing) ->
transformation.runner (clean/validate/standardize/load) -> queryable
SQLite table. This is the closest thing to "does the whole pipeline work"
without a live Postgres instance.
"""
import httpx
import respx
from sqlalchemy import create_engine, select

from knbs_cbk_pipeline.ingestion import runner as ingestion_runner
from knbs_cbk_pipeline.transformation import runner as transform_runner
from knbs_cbk_pipeline.warehouse.tables import economic_indicators


@respx.mock
def test_ingest_then_transform_then_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()

    sources_yaml = """
sources:
  - id: cbk_fx_rates
    owner: cbk
    extractor: cbk_extractor
    fetch_mode: api_json
    endpoint: "https://api.frankfurter.dev/v2/latest"
    params: {providers: CBK, base: USD}
    format: json
"""
    (tmp_path / "config" / "sources.yaml").write_text(sources_yaml)

    from config.settings import settings
    monkeypatch.setattr(settings, "sources_config_path", tmp_path / "config" / "sources.yaml")
    monkeypatch.setattr(settings, "raw_data_dir", tmp_path / "data" / "raw")
    monkeypatch.setattr(
        "knbs_cbk_pipeline.observability.run_metadata.RUN_LOG_PATH",
        tmp_path / "data" / "curated" / "_run_metadata.jsonl",
    )

    respx.get("https://api.frankfurter.dev/v2/latest").mock(
        return_value=httpx.Response(
            200,
            json={"amount": 1.0, "base": "USD", "date": "2026-09-02", "rates": {"KES": 129.31}},
            headers={"content-type": "application/json"},
        )
    )

    ingestion_runs = ingestion_runner.run_all()
    assert all(r.success for r in ingestion_runs)

    engine = create_engine("sqlite:///:memory:")
    results = transform_runner.transform_and_load_all(source_ids=["cbk_fx_rates"], engine=engine)
    assert results["cbk_fx_rates"] == 1

    with engine.connect() as conn:
        rows = conn.execute(select(economic_indicators)).fetchall()
    assert len(rows) == 1
    assert rows[0].indicator_code == "cbk_fx_usd_kes"
    assert rows[0].value == 129.31
