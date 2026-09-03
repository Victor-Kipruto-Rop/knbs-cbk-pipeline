"""
Refreshes the dbt-built marts. Runs daily after the CBK DAG's typical
completion time; the KNBS DAG's monthly load will simply be picked up by
the next daily refresh rather than needing its own dbt trigger — marts are
build-from-staging, so an extra dbt run when nothing new landed is cheap
and safe (dbt only rebuilds what changed).
"""
from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": dt.timedelta(minutes=10),
}


@dag(
    dag_id="warehouse_refresh",
    schedule="0 8 * * *",  # 08:00 daily, after cbk_daily_ingestion's 06:00 run
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["knbs-cbk-pipeline", "dbt", "daily"],
)
def warehouse_refresh():
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="cd /opt/pipeline/dbt && dbt run --profiles-dir .",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/pipeline/dbt && dbt test --profiles-dir .",
    )

    @task
    def alert_on_test_failure() -> None:
        # Placeholder hook: wire to observability/alerts.py if dbt test
        # failures should page the same channel as pipeline run failures.
        pass

    dbt_run >> dbt_test >> alert_on_test_failure()


warehouse_refresh()
