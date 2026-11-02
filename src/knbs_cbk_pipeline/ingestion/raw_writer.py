"""Immutable raw landing with content checksums and atomic sidecar writes."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import structlog
from config.settings import settings
from knbs_cbk_pipeline.ingestion.base_extractor import ExtractionResult

log = structlog.get_logger()
_EXT_BY_CONTENT_TYPE = {
    "application/json": "json", "text/html": "html",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv", "application/pdf": "pdf",
}

def _extension_for(result: ExtractionResult) -> str:
    return _EXT_BY_CONTENT_TYPE.get(result.content_type, "bin")

def write_raw(result: ExtractionResult, base_dir: Path | None = None) -> Path:
    base_dir = base_dir or settings.raw_data_dir
    fetched = result.fetched_at
    target_dir = base_dir / result.source_id / f"{fetched:%Y}" / f"{fetched:%m}" / f"{fetched:%d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(result.content).hexdigest()
    ext = _extension_for(result)
    filename = f"{result.source_id}_{fetched:%Y%m%dT%H%M%S}_{fetched.microsecond:06d}_{checksum[:12]}.{ext}"
    file_path = target_dir / filename
    temporary = file_path.with_suffix(file_path.suffix + ".tmp")
    temporary.write_bytes(result.content)
    os.replace(temporary, file_path)
    metadata = {
        "source_id": result.source_id, "source_url": result.source_url,
        "fetched_at": fetched.isoformat(), "content_type": result.content_type,
        "byte_size": len(result.content), "checksum_sha256": checksum, **result.metadata,
    }
    meta_path = file_path.with_suffix(file_path.suffix + ".meta.json")
    meta_tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    meta_tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(meta_tmp, meta_path)
    log.info("raw_writer.written", path=str(file_path), bytes=len(result.content), checksum_sha256=checksum)
    return file_path
