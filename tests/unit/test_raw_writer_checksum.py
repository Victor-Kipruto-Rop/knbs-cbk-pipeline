import datetime as dt
import hashlib
import json
from knbs_cbk_pipeline.ingestion.base_extractor import ExtractionResult
from knbs_cbk_pipeline.ingestion.raw_writer import write_raw

def test_raw_writer_persists_checksum_and_unique_artifact(tmp_path):
    fetched = dt.datetime(2026, 10, 1, 6, 0, 0, 123456, tzinfo=dt.timezone.utc)
    result = ExtractionResult("cbk_fx_rates", fetched, b'{"ok":true}', "application/json", "https://example.test")
    path = write_raw(result, tmp_path)
    sidecar = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text())
    assert sidecar["checksum_sha256"] == hashlib.sha256(result.content).hexdigest()
    assert sidecar["byte_size"] == len(result.content)
    assert path.read_bytes() == result.content
