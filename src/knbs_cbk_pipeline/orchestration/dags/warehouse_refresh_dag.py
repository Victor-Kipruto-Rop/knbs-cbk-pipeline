"""Daily dbt refresh after source ingestion DAGs have landed new observations."""
from __future__ import annotations
import datetime as dt
from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.operators.python import get_current_context
from airflow.utils.trigger_rule import TriggerRule

default_args = {"owner": "data-eng", "retries": 2, "retry_delay": dt.timedelta(minutes=10)}

@dag(
    dag_id="warehouse_refresh",
    schedule="0 8 * * *",
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["knbs-cbk-pipeline", "dbt", "daily"],
)
def warehouse_refresh():
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="cd /opt/airflow/project/dbt && dbt deps && dbt build --profiles-dir .",
    )

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def alert_on_refresh_failure() -> None:
        context = get_current_context()
        dag_run = context["dag_run"]
        failed = [
            task_instance.task_id
            for task_instance in dag_run.get_task_instances()
            if task_instance.task_id != "alert_on_refresh_failure"
            and task_instance.state == "failed"
        ]
        if failed:
            from knbs_cbk_pipeline.observability.alerts import send_alert
            send_alert(f"KNBS/CBK dbt refresh failed: {', '.join(failed)}")

    alert_task = alert_on_refresh_failure()
    dbt_build >> alert_task

warehouse_refresh()
