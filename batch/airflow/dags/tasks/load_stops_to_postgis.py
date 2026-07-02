import io
import logging

import polars as pl
from tasks.utils import CopyProgressReader, get_minio_client, get_postgis_conn

logger = logging.getLogger(__name__)


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    client = get_minio_client()

    logger.info("Reading stops.parquet from MinIO...")
    response = client.get_object("raw-data", f"{run_id}/stops.parquet")
    buf = io.BytesIO(response.read())
    df = pl.read_parquet(buf)
    logger.info(
        "Loaded %s rows, %s columns from parquet", f"{len(df):,}", len(df.columns)
    )

    staging_cols = ["stop_id", "stop_code", "stop_name", "stop_lon", "stop_lat"]

    logger.info("Converting to CSV...")
    csv_buf = io.StringIO()
    df.select(staging_cols).write_csv(csv_buf)
    csv_str = csv_buf.getvalue()
    logger.info("CSV buffer: %s bytes", f"{len(csv_str):,}")

    conn = get_postgis_conn()
    with conn.cursor() as cur:
        logger.info("Truncating PostGIS stops...")
        cur.execute("TRUNCATE TABLE stops;")

        logger.info("Creating staging table...")
        cur.execute("""
            CREATE TEMP TABLE stops_staging (
                stop_id TEXT, stop_code TEXT, stop_name TEXT,
                stop_lon DOUBLE PRECISION, stop_lat DOUBLE PRECISION
            )
        """)

        logger.info("Copying to staging...")
        reader = CopyProgressReader(csv_str, len(csv_str), "stops_staging")
        cur.copy_expert(
            "COPY stops_staging (stop_id, stop_code, stop_name, stop_lon, stop_lat) "
            "FROM STDIN CSV HEADER",
            reader,
        )

        logger.info("Inserting with geometry...")
        cur.execute("""
            INSERT INTO stops (stop_id, stop_code, stop_name, geom)
            SELECT
                stop_id, stop_code, stop_name,
                ST_SetSRID(ST_MakePoint(stop_lon, stop_lat), 4326)
            FROM stops_staging
        """)
        logger.info("Inserted %s rows", cur.rowcount)

    conn.commit()
    conn.close()

    logger.info("Loaded %s stops into PostGIS", f"{len(df):,}")

