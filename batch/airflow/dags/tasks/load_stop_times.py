import io
import logging

import polars as pl
from tasks.utils import CopyProgressReader, get_minio_client, get_pg_conn

logger = logging.getLogger(__name__)


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    client = get_minio_client()

    logger.info("Reading stop_times.parquet from MinIO...")
    response = client.get_object("raw-data", f"{run_id}/stop_times.parquet")
    buf = io.BytesIO(response.read())
    df = pl.read_parquet(buf)
    logger.info(
        "Loaded %s rows, %s columns from parquet", f"{len(df):,}", len(df.columns)
    )

    cols = [
        "trip_id",
        "arrival_time",
        "departure_time",
        "stop_id",
        "stop_sequence",
        "pickup_type",
        "drop_off_type",
    ]

    logger.info("Converting to CSV...")
    csv_buf = io.StringIO()
    df.select(cols).write_csv(csv_buf)
    csv_str = csv_buf.getvalue()
    logger.info("CSV buffer: %s bytes", f"{len(csv_str):,}")

    conn = get_pg_conn()
    with conn.cursor() as cur:
        logger.info("Truncating table stop_times...")
        cur.execute("TRUNCATE TABLE stop_times;")

        logger.info("Copying to PostgreSQL...")
        reader = CopyProgressReader(csv_str, len(csv_str), "stop_times")
        cur.copy_expert(
            "COPY stop_times (trip_id, arrival_time, departure_time, "
            "stop_id, stop_sequence, pickup_type, drop_off_type) "
            "FROM STDIN CSV HEADER",
            reader,
        )

    conn.commit()
    conn.close()

    logger.info("Loaded %s rows into stop_times", f"{len(df):,}")

