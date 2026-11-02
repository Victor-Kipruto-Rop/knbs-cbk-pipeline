"""Source registry dispatcher and raw landing entry point."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from config.settings import settings
from knbs_cbk_pipeline.ingestion.base_extractor import BaseExtractor
from knbs_cbk_pipeline.ingestion.cbk_extractor import CBKExtractor
from knbs_cbk_pipeline.ingestion.knbs_extractor import KNBSExtractor
from knbs_cbk_pipeline.ingestion.raw_writer import write_raw
from knbs_cbk_pipeline.observability.run_metadata import RunRecord, record_run

log = structlog.get_logger()
_EXTRACTORS: dict[str, type[BaseExtractor]] = {"cbk_extractor": CBKExtractor, "knbs_extractor": KNBSExtractor}


def load_sources(config_path: Path | None = None) -> list[dict[str, Any]]:
    path = config_path or settings.sources_config_path
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise ValueError(f"Invalid source registry: expected a sources list in {path}")
    ids = [source.get("id") for source in sources]
    if any(not source_id for source_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("Source registry contains missing or duplicate source IDs")
    return sources


def run_source(source_config: dict[str, Any]) -> RunRecord:
    source_id = source_config["id"]
    try:
        extractor_cls = _EXTRACTORS[source_config["extractor"]]
        with extractor_cls() as extractor:
            result = extractor.safe_fetch(source_config)
            path = write_raw(result)
        run = RunRecord.mark_success(source_id, raw_path=path, byte_size=len(result.content))
    except Exception as exc:
        log.exception("runner.source_failed", source_id=source_id, error=str(exc))
        run = RunRecord.mark_failure(source_id, error=str(exc))
    record_run(run)
    return run


def run_all(source_ids: list[str] | None = None) -> list[RunRecord]:
    settings.ensure_dirs()
    sources = load_sources()
    if source_ids is not None:
        unknown = set(source_ids) - {source["id"] for source in sources}
        if unknown:
            raise ValueError(f"Unknown source IDs: {sorted(unknown)}")
        sources = [source for source in sources if source["id"] in set(source_ids)]
    runs = [run_source(source) for source in sources]
    failed = [run.source_id for run in runs if not run.success]
    if failed:
        log.error("runner.completed_with_failures", failed=failed)
    else:
        log.info("runner.completed", sources=len(runs))
    return runs


if __name__ == "__main__":
    raise SystemExit(1 if any(not run.success for run in run_all()) else 0)
