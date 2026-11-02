"""
End-to-end test of the ingestion stage: source registry -> extractor
dispatch -> raw landing -> run metadata. Mocks all network calls so it's
safe to run anywhere, including this sandbox.
"""
import json

import httpx
import respx

from knbs_cbk_pipeline.ingestion import runner
from knbs_cbk_pipeline.observability.run_metadata import read_recent_runs


@respx.mock
def test_run_all_lands_raw_files_and_records_runs(tmp_path, monkeypatch):
    # Redirect storage to a temp dir so the test never touches the real repo data/
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

  - id: knbs_cpi
    owner: knbs
    extractor: knbs_extractor
    fetch_mode: file_download
    endpoint: "https://www.knbs.or.ke/download/consumer-price-index-cpi/"
    format: xlsx
"""
    (tmp_path / "config" / "sources.yaml").write_text(sources_yaml)

    from config.settings import settings
    monkeypatch.setattr(settings, "sources_config_path", tmp_path / "config" / "sources.yaml")
    monkeypatch.setattr(settings, "raw_data_dir", tmp_path / "data" / "raw")
    monkeypatch.setattr(settings, "staging_data_dir", tmp_path / "data" / "staging")
    monkeypatch.setattr(settings, "curated_data_dir", tmp_path / "data" / "curated")
    monkeypatch.setattr(runner, "RUN_LOG_PATH", tmp_path / "data" / "curated" / "_run_metadata.jsonl", raising=False)
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
    respx.get("https://www.knbs.or.ke/download/consumer-price-index-cpi/").mock(
        return_value=httpx.Response(
            200,
            content=b"PK\\x03\\x04fake-xlsx-bytes",
            headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        )
    )

    runs = runner.run_all()

    assert len(runs) == 2
    assert all(r.success for r in runs)

    raw_dir = tmp_path / "data" / "raw"
    fx_files = [p for p in (raw_dir / "cbk_fx_rates").rglob("*.json") if not p.name.endswith(".meta.json")]
    cpi_files = [p for p in (raw_dir / "knbs_cpi").rglob("*.xlsx") if not p.name.endswith(".meta.json")]
    assert len(fx_files) == 1
    assert len(cpi_files) == 1

    fx_content = json.loads(fx_files[0].read_text())
    assert fx_content["rates"]["KES"] == 129.31

    recent = read_recent_runs()
    assert len(recent) == 2
    assert {r["source_id"] for r in recent} == {"cbk_fx_rates", "knbs_cpi"}
