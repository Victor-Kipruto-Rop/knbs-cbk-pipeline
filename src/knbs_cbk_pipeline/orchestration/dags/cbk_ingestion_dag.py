"""
Daily DAG for CBK's daily-cadence sources (FX rates, key policy rates).
Business logic lives entirely in knbs_cbk_pipeline.ingestion.runner and
knbs_cbk_pipeline.transformation.runner — this file only schedules and
sequences, per the orchestration principle in the project's data-engineer
skill: no hidden side effects in DAG files.
"""
from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task

DAILY_CBK_SOURCES = ["cbk_fx_rates", "cbk_key_rates"]

default_args = {
    "owner": "data-eng",
    "retries": 3,
    "retry_delay": dt.timedelta(minutes=5),
}


@dag(
    dag_id="cbk_daily_ingestion",
    schedule="0 6 * * *",  # 06:00 daily
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["knbs-cbk-pipeline", "cbk", "daily"],
)
def cbk_daily_ingestion():
    @task
    def ingest() -> list[str]:
        from knbs_cbk_pipeline.ingestion.runner import run_all

        runs = run_all(source_ids=DAILY_CBK_SOURCES)
        failed = [r.source_id for r in runs if not r.success]
        if failed:
            raise RuntimeError(f"Ingestion failed for: {failed}")
        return [r.source_id for r in runs]

    @task
    def transform(source_ids: list[str]) -> dict[str, int]:
        from knbs_cbk_pipeline.transformation.runner import transform_and_load_all

        results = transform_and_load_all(source_ids=source_ids)
        failed = {sid: n for sid, n in results.items() if n < 0}
        if failed:
            raise RuntimeError(f"Transformation failed for: {list(failed)}")
        return results

    @task
    def check_health() -> None:
        from knbs_cbk_pipeline.observability.alerts import check_and_alert
        from knbs_cbk_pipeline.observability.metrics import freshness_by_source
        from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import get_engine

        health = freshness_by_source(get_engine())
        check_and_alert(health)

    ingested = ingest()
    transformed = transform(ingested)
    transformed >> check_health()


cbk_daily_ingestion()
