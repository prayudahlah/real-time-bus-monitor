from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import TaskGroup

from tasks.extract import main as extract
from tasks.load_routes import main as load_routes
from tasks.load_stops import main as load_stops
from tasks.load_trips import main as load_trips
from tasks.load_stop_times import main as load_stop_times
from tasks.feature_eng import main as feature_eng
from tasks.train import main as train
from tasks.validate_data import main as validate_data

default_args = {
    "owner": "ipbd",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
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

        load_routes_task >> load_trips_task >> load_stop_times_task
        load_stops_task >> load_stop_times_task

    validate_data_task = PythonOperator(
        task_id="validate_data",
        python_callable=validate_data,
    )

    feature_eng_task = PythonOperator(
        task_id="feature_eng",
        python_callable=feature_eng,
    )

    train_task = PythonOperator(
        task_id="train",
        python_callable=train,
    )

    extract_task >> load_group >> validate_data_task >> feature_eng_task >> train_task
