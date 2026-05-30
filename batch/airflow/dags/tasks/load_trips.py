import io
import logging

import polars as pl
from tasks.utils import CopyProgressReader, get_minio_client, get_pg_conn

logger = logging.getLogger(__name__)


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    client = get_minio_client()

    logger.info("Reading trips.parquet from MinIO...")
    response = client.get_object("raw-data", f"{run_id}/trips.parquet")
    buf = io.BytesIO(response.read())
    df = pl.read_parquet(buf)
    logger.info(
        "Loaded %s rows, %s columns from parquet", f"{len(df):,}", len(df.columns)
    )

    cols = [
        "route_id",
        "service_id",
        "trip_id",
        "trip_headsign",
        "direction_id",
        "shape_id",
    ]

    logger.info("Converting to CSV...")
    csv_buf = io.StringIO()
    df.select(cols).write_csv(csv_buf)
    csv_str = csv_buf.getvalue()
    logger.info("CSV buffer: %s bytes", f"{len(csv_str):,}")

    conn = get_pg_conn()
    with conn.cursor() as cur:
        logger.info("Truncating table trips...")
        cur.execute("TRUNCATE TABLE trips CASCADE;")

        logger.info("Copying to PostgreSQL...")
        reader = CopyProgressReader(csv_str, len(csv_str), "trips")
        cur.copy_expert(
            "COPY trips (route_id, service_id, trip_id, trip_headsign, "
            "direction_id, shape_id) "
            "FROM STDIN CSV HEADER",
            reader,
        )

    conn.commit()
    conn.close()

    logger.info("Loaded %s rows into trips", f"{len(df):,}")
