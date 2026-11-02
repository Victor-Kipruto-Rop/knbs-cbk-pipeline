"""Quarterly GDP bulletin ingestion, isolated from the monthly CPI cadence."""
from __future__ import annotations
import datetime as dt
from airflow.decorators import dag, task

GDP_SOURCE = ["knbs_gdp_quarterly"]

@dag(
    dag_id="knbs_gdp_quarterly_ingestion",
    schedule="0 7 1 1,4,7,10 *",
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    default_args={"owner": "data-eng", "retries": 2, "retry_delay": dt.timedelta(minutes=20)},
    tags=["knbs-cbk-pipeline", "knbs", "quarterly", "gdp"],
)
def knbs_gdp_quarterly_ingestion():
    @task
    def ingest() -> list[str]:
        from knbs_cbk_pipeline.ingestion.runner import run_all
        runs = run_all(source_ids=GDP_SOURCE)
        failed = [run.source_id for run in runs if not run.success]
        if failed:
            raise RuntimeError(f"GDP ingestion failed: {failed}")
        return [run.source_id for run in runs]

    @task
    def transform(source_ids: list[str]) -> dict[str, int]:
        from knbs_cbk_pipeline.transformation.runner import transform_and_load_all
        results = transform_and_load_all(source_ids=source_ids)
        failed = [source for source, rows in results.items() if rows < 0]
        if failed:
            raise RuntimeError(f"GDP transformation failed: {failed}; inspect the KNBS workbook layout")
        return results

    transform(ingest())

knbs_gdp_quarterly_ingestion()
