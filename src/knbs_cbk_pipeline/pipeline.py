"""One-shot local pipeline: ingest, transform/load, then build and test dbt marts."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
import structlog
from knbs_cbk_pipeline.ingestion.runner import run_all
from knbs_cbk_pipeline.transformation.runner import transform_and_load_all

log = structlog.get_logger()

def main() -> int:
    ingestion = run_all()
    failed_ingestion = [run.source_id for run in ingestion if not run.success]
    if failed_ingestion:
        log.error("pipeline.ingestion_failed", sources=failed_ingestion)
        return 1
    transformed = transform_and_load_all(source_ids=[run.source_id for run in ingestion])
    failed_transform = [source for source, rows in transformed.items() if rows < 0]
    if failed_transform:
        log.error("pipeline.transformation_failed", sources=failed_transform)
        return 1
    dbt = shutil.which("dbt")
    if not dbt:
        log.error("pipeline.dbt_missing", hint="Install the analytics extra: pip install -e '.[analytics]'")
        return 2
    dbt_dir = Path("dbt")
    for command in ([dbt, "deps"], [dbt, "build", "--profiles-dir", "."]):
        result = subprocess.run(command, cwd=dbt_dir, check=False)
        if result.returncode:
            log.error("pipeline.dbt_failed", command=command, exit_code=result.returncode)
            return result.returncode
    log.info("pipeline.completed", ingested=len(ingestion), transformed=transformed)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
