import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import TaskGroup

from tasks.extract import main as extract
from tasks.clear_tables import main as clear_tables
from tasks.load_routes import main as load_routes
from tasks.load_stops import main as load_stops
from tasks.load_trips import main as load_trips
from tasks.load_stop_times import main as load_stop_times
from tasks.load_calendar import main as load_calendar
from tasks.load_calendar_dates import main as load_calendar_dates
from tasks.load_agency import main as load_agency
from tasks.load_stops_to_postgis import main as load_stops_to_postgis
from tasks.load_shapes_to_postgis import main as load_shapes_to_postgis
from tasks.feature_eng import main as feature_eng
from tasks.train import main as train
from tasks.soda_scan import main as soda_scan

def _send_telegram(context, status, icon):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    topic_id = os.environ.get("TELEGRAM_PIPELINE_TOPIC_ID")
    if not bot_token or not chat_id:
        return

    dag_id = context["dag"].dag_id
    task_id = context["task"].task_id
    run_id = context["run_id"]
    log_url = context["task_instance"].log_url

    text = (
        f"{icon} Pipeline {status}\n"
        f"DAG: {dag_id}\n"
        f"Task: {task_id}\n"
        f"Run: {run_id}\n"
        f"Log: {log_url}"
    )
    exception = context.get("exception")
    if exception:
        text += f"\nError: {str(exception)[:200]}"

    payload = {"chat_id": chat_id, "text": text}
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload,
            timeout=5,
        )
    except Exception:
        pass


def _send_telegram_alert(context):
    _send_telegram(context, "Gagal", "\u274c")


def _send_telegram_success(context):
    _send_telegram(context, "Berhasil", "\u2705")


default_args = {
    "owner": "ipbd",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": _send_telegram_alert,
    "on_success_callback": _send_telegram_success,
}

with DAG(
    "batch_pipeline",
    default_args=default_args,
    description="Batch pipeline: Extract GTFS → Load PostgreSQL → Feature Engineering → Train model",
    schedule="0 6 * * 1",
    start_date=datetime(2026, 5, 30),
    catchup=False,
    tags=["batch", "gtfs", "wmata"],
) as dag:
    extract_task = PythonOperator(
        task_id="extract",
        python_callable=extract,
    )

    clear_tables_task = PythonOperator(
        task_id="clear_tables",
        python_callable=clear_tables,
    )

    with TaskGroup(
        "load_to_postgres", tooltip="Load GTFS data into PostgreSQL"
    ) as load_group:
        load_routes_task = PythonOperator(
            task_id="load_routes",
            python_callable=load_routes,
        )

        load_stops_task = PythonOperator(
            task_id="load_stops",
            python_callable=load_stops,
        )

        load_trips_task = PythonOperator(
            task_id="load_trips",
            python_callable=load_trips,
        )

        load_stop_times_task = PythonOperator(
            task_id="load_stop_times",
            python_callable=load_stop_times,
        )

        load_calendar_task = PythonOperator(
            task_id="load_calendar",
            python_callable=load_calendar,
        )

        load_calendar_dates_task = PythonOperator(
            task_id="load_calendar_dates",
            python_callable=load_calendar_dates,
        )

        load_agency_task = PythonOperator(
            task_id="load_agency",
            python_callable=load_agency,
        )

        load_routes_task >> load_trips_task >> load_stop_times_task
        load_stops_task >> load_stop_times_task
        load_calendar_task >> load_calendar_dates_task

    with TaskGroup(
        "load_to_postgis", tooltip="Load spatial data into PostGIS"
    ) as load_postgis_group:
        load_stops_geom_task = PythonOperator(
            task_id="load_stops_geom",
            python_callable=load_stops_to_postgis,
        )

        load_shapes_task = PythonOperator(
            task_id="load_shapes",
            python_callable=load_shapes_to_postgis,
        )

    train_task = PythonOperator(
        task_id="train",
        python_callable=train,
    )

    soda_scan_task = PythonOperator(
        task_id="soda_scan",
        python_callable=soda_scan,
    )

    feature_eng_task = PythonOperator(
        task_id="feature_eng",
        python_callable=feature_eng,
    )

    (
        extract_task
        >> clear_tables_task
        >> [load_group, load_postgis_group]
        >> soda_scan_task
        >> feature_eng_task
        >> train_task
    )
