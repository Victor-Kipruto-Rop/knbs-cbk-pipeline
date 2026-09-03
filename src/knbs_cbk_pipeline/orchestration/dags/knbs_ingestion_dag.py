"""
Monthly/quarterly DAG for KNBS bulletins (CPI, GDP). Separate from the CBK
daily DAG because the cadence and failure profile are genuinely different —
KNBS sources are file downloads that change layout between releases far
more often than CBK's feeds, so this DAG's transform step is more likely
to need a human look when it fails.
"""
from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task

MONTHLY_KNBS_SOURCES = ["knbs_cpi"]

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": dt.timedelta(minutes=15),
}


@dag(
    dag_id="knbs_bulletin_ingestion",
    schedule="0 7 15 * *",  # 15th of each month, 07:00 — KNBS's typical CPI release window
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["knbs-cbk-pipeline", "knbs", "monthly"],
)
def knbs_bulletin_ingestion():
    @task
    def ingest() -> list[str]:
        from knbs_cbk_pipeline.ingestion.runner import run_all

        runs = run_all(source_ids=MONTHLY_KNBS_SOURCES)
        failed = [r.source_id for r in runs if not r.success]
        if failed:
            raise RuntimeError(f"Ingestion failed for: {failed}")
        return [r.source_id for r in runs]

    @task
    def transform(source_ids: list[str]) -> dict[str, int]:
        from knbs_cbk_pipeline.transformation.runner import transform_and_load_all

        # KNBS layout drift is expected here — a validation failure should
        # alert loudly rather than retry blindly into the same bad parse.
        results = transform_and_load_all(source_ids=source_ids)
        failed = {sid: n for sid, n in results.items() if n < 0}
        if failed:
            raise RuntimeError(
                f"Transformation failed for: {list(failed)} — likely a KNBS "
                "bulletin layout change, check transformation/cleaners/knbs_cleaner.py"
            )
        return results

    ingested = ingest()
    transform(ingested)


knbs_bulletin_ingestion()
