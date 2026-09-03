"""
Entry point that ties the source registry (config/sources.yaml) to the
right extractor and lands results via raw_writer. This is what both the
CLI script and the Airflow DAGs call — orchestration should never contain
business logic, only scheduling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from config.settings import settings
from knbs_cbk_pipeline.ingestion.base_extractor import BaseExtractor, ExtractionError
from knbs_cbk_pipeline.ingestion.cbk_extractor import CBKExtractor
from knbs_cbk_pipeline.ingestion.knbs_extractor import KNBSExtractor
from knbs_cbk_pipeline.ingestion.raw_writer import write_raw
from knbs_cbk_pipeline.observability.run_metadata import RunRecord, record_run

log = structlog.get_logger()

_EXTRACTORS: dict[str, type[BaseExtractor]] = {
    "cbk_extractor": CBKExtractor,
    "knbs_extractor": KNBSExtractor,
}


def load_sources(config_path: Path | None = None) -> list[dict[str, Any]]:
    config_path = config_path or settings.sources_config_path
    with open(config_path) as f:
        return yaml.safe_load(f)["sources"]


def run_source(source_config: dict[str, Any]) -> RunRecord:
    """Fetch + land a single source, recording success/failure either way."""
    extractor_name = source_config["extractor"]
    extractor_cls = _EXTRACTORS.get(extractor_name)
    if extractor_cls is None:
        raise ValueError(f"Unknown extractor '{extractor_name}' for source '{source_config['id']}'")

    with extractor_cls() as extractor:
        try:
            result = extractor.safe_fetch(source_config)
            path = write_raw(result)
            run = RunRecord.mark_success(source_config["id"], raw_path=path, byte_size=len(result.content))
        except ExtractionError as exc:
            run = RunRecord.mark_failure(source_config["id"], error=str(exc))

    record_run(run)
    return run


def run_all(source_ids: list[str] | None = None) -> list[RunRecord]:
    """Run ingestion for all configured sources, or a filtered subset."""
    settings.ensure_dirs()
    sources = load_sources()
    if source_ids:
        sources = [s for s in sources if s["id"] in source_ids]

    runs = []
    for source_config in sources:
        log.info("runner.starting", source_id=source_config["id"])
        runs.append(run_source(source_config))

    failed = [r for r in runs if not r.success]
    if failed:
        log.warning("runner.completed_with_failures", failed=[r.source_id for r in failed])
    else:
        log.info("runner.completed", sources=len(runs))
    return runs


if __name__ == "__main__":
    run_all()
