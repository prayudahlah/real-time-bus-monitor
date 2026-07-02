import io
import logging

import polars as pl
from tasks.utils import CopyProgressReader, get_minio_client, get_postgis_conn

logger = logging.getLogger(__name__)


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    client = get_minio_client()

    logger.info("Reading shapes.parquet from MinIO...")
    response = client.get_object("raw-data", f"{run_id}/shapes.parquet")
    buf = io.BytesIO(response.read())
    df = pl.read_parquet(buf)
    logger.info(
        "Loaded %s rows, %s columns from parquet", f"{len(df):,}", len(df.columns)
    )

    cols = ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]

    logger.info("Converting to CSV...")
    csv_buf = io.StringIO()
    df.select(cols).write_csv(csv_buf)
    csv_str = csv_buf.getvalue()
    logger.info("CSV buffer: %s bytes", f"{len(csv_str):,}")

    conn = get_postgis_conn()
    with conn.cursor() as cur:
        logger.info("Truncating route_paths...")
        cur.execute("TRUNCATE TABLE route_paths;")

        logger.info("Creating staging table...")
        cur.execute("""
            CREATE TEMP TABLE shape_points (
                shape_id TEXT,
                shape_pt_lat DOUBLE PRECISION,
                shape_pt_lon DOUBLE PRECISION,
                shape_pt_sequence INTEGER
            )
        """)

        logger.info("Copying to staging...")
        reader = CopyProgressReader(csv_str, len(csv_str), "shape_points")
        cur.copy_expert(
            "COPY shape_points (shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence) "
            "FROM STDIN CSV HEADER",
            reader,
        )

        logger.info("Aggregating into LINESTRINGs...")
        cur.execute("""
            INSERT INTO route_paths (shape_id, geom)
            SELECT
                shape_id,
                ST_SetSRID(
                    ST_MakeLine(
                        ST_MakePoint(shape_pt_lon, shape_pt_lat)
                        ORDER BY shape_pt_sequence
                    ),
                    4326
                )
            FROM shape_points
            GROUP BY shape_id
        """)
        logger.info("Created %s route paths", cur.rowcount)

    conn.commit()
    conn.close()

    logger.info("Loaded shapes into PostGIS")

