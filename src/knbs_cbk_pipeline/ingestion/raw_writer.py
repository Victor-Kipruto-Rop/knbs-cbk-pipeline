"""
Lands every ExtractionResult to the raw zone before any parsing/cleaning
happens. Raw files are immutable and timestamped — this is what makes
backfill and replay possible: if a transformation bug is found, raw data
never has to be re-fetched, only re-processed.

Layout:
    data/raw/{source_id}/{yyyy}/{mm}/{dd}/{source_id}_{fetched_at_iso}.{ext}
"""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from config.settings import settings
from knbs_cbk_pipeline.ingestion.base_extractor import ExtractionResult

log = structlog.get_logger()

_EXT_BY_CONTENT_TYPE = {
    "application/json": "json",
    "text/html": "html",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "application/pdf": "pdf",
}


def _extension_for(result: ExtractionResult) -> str:
    return _EXT_BY_CONTENT_TYPE.get(result.content_type, "bin")


def write_raw(result: ExtractionResult, base_dir: Path | None = None) -> Path:
    base_dir = base_dir or settings.raw_data_dir
    fetched = result.fetched_at
    target_dir = base_dir / result.source_id / f"{fetched:%Y}" / f"{fetched:%m}" / f"{fetched:%d}"
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = _extension_for(result)
    filename = f"{result.source_id}_{fetched:%Y%m%dT%H%M%SZ}.{ext}"
    file_path = target_dir / filename
    file_path.write_bytes(result.content)

    # Sidecar metadata: what was fetched, from where, and when — this is
    # what run_metadata / lineage docs read from later.
    meta_path = file_path.with_suffix(file_path.suffix + ".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "source_id": result.source_id,
                "source_url": result.source_url,
                "fetched_at": fetched.isoformat(),
                "content_type": result.content_type,
                "byte_size": len(result.content),
                **result.metadata,
            },
            indent=2,
        )
    )

    log.info("raw_writer.written", path=str(file_path), bytes=len(result.content))
    return file_path
