import io
import logging

import polars as pl
from tasks.utils import CopyProgressReader, get_minio_client, get_pg_conn

logger = logging.getLogger(__name__)


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    client = get_minio_client()

    logger.info("Reading calendar.parquet from MinIO...")
    response = client.get_object("raw-data", f"{run_id}/calendar.parquet")
    buf = io.BytesIO(response.read())
    df = pl.read_parquet(buf)
    logger.info(
        "Loaded %s rows, %s columns from parquet", f"{len(df):,}", len(df.columns)
    )

    cols = [
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ]

    logger.info("Converting to CSV...")
    csv_buf = io.StringIO()
    df.select(cols).write_csv(csv_buf)
    csv_str = csv_buf.getvalue()
    logger.info("CSV buffer: %s bytes", f"{len(csv_str):,}")

    conn = get_pg_conn()
    with conn.cursor() as cur:
        logger.info("Truncating table calendar...")
        cur.execute("TRUNCATE TABLE calendar;")

        logger.info("Copying to PostgreSQL...")
        reader = CopyProgressReader(csv_str, len(csv_str), "calendar")
        cur.copy_expert(
            "COPY calendar (service_id, monday, tuesday, wednesday, thursday, "
            "friday, saturday, sunday, start_date, end_date) "
            "FROM STDIN CSV HEADER",
            reader,
        )

    conn.commit()
    conn.close()

    logger.info("Loaded %s rows into calendar", f"{len(df):,}")

