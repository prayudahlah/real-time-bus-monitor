import io
import logging

import polars as pl
from tasks.utils import get_minio_client, get_pg_conn

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "distance_to_next_m",
    "stop_sequence",
    "hour_of_day",
    "stop_position_pct",
    "travel_time_sec",
]
SPEED_MAX = 30
DISTANCE_MAX = 5000


def _time_to_sec(col):
    parts = col.str.split(":")
    return (
        parts.list.get(0).cast(pl.Int64) * 3600
        + parts.list.get(1).cast(pl.Int64) * 60
        + parts.list.get(2).cast(pl.Int64)
    )


def _load_data(conn):
    stop_times = pl.read_database(
        "SELECT trip_id, arrival_time, stop_id, stop_sequence FROM stop_times",
        conn,
    )
    stops = pl.read_database("SELECT stop_id, stop_lat, stop_lon FROM stops", conn)
    logger.info(
        "Read %s stop_times, %s stops from PostgreSQL",
        f"{len(stop_times):,}",
        f"{len(stops):,}",
    )
    return stop_times.join(stops, on="stop_id", how="left").sort(
        ["trip_id", "stop_sequence"]
    )


def _compute_features(df):
    return (
        df.lazy()
        .with_columns(total_stops=pl.len().over("trip_id"))
        .with_columns(
            pl.col("stop_lat").shift(-1).over("trip_id").alias("lat_next"),
            pl.col("stop_lon").shift(-1).over("trip_id").alias("lon_next"),
        )
        .with_columns(lat_mid=(pl.col("stop_lat") + pl.col("lat_next")) / 2)
        .with_columns(
            dx=(pl.col("lon_next") - pl.col("stop_lon"))
            * 111320
            * pl.col("lat_mid").radians().cos(),
            dy=(pl.col("lat_next") - pl.col("stop_lat")) * 111320,
        )
        .with_columns(
            distance_to_next_m=(pl.col("dx") ** 2 + pl.col("dy") ** 2).sqrt()
        )
        .with_columns(arrival_sec=_time_to_sec(pl.col("arrival_time")))
        .with_columns(
            arrival_next_sec=pl.col("arrival_sec").shift(-1).over("trip_id"),
        )
        .with_columns(
            travel_time_sec=pl.col("arrival_next_sec") - pl.col("arrival_sec")
        )
        .with_columns(
            hour_of_day=((pl.col("arrival_sec") / 3600).floor().cast(pl.Int64) % 24),
        )
        .with_columns(
            stop_position_pct=pl.col("stop_sequence").cast(pl.Float64)
            / pl.col("total_stops"),
        )
        .with_columns(
            speed_est_mps=pl.col("distance_to_next_m") / pl.col("travel_time_sec"),
        )
        .collect()
    )


def _clean_and_sample(df):
    before = len(df)
    df = df.drop_nulls(["distance_to_next_m", "travel_time_sec", "speed_est_mps"])
    df = df.filter(
        (pl.col("travel_time_sec") > 0)
        & (pl.col("speed_est_mps") < SPEED_MAX)
        & (pl.col("distance_to_next_m") < DISTANCE_MAX)
    )
    logger.info(
        "Cleaning: %s → %s rows (%s removed)",
        f"{before:,}",
        f"{len(df):,}",
        f"{before - len(df):,}",
    )
    if len(df) > 500_000:
        df = df.sample(n=500_000, seed=42)
        logger.info("Sampled to 500,000 rows")
    return df


def _upload_to_minio(run_id, df):
    client = get_minio_client()
    buf = io.BytesIO()
    df.write_parquet(buf)
    size = buf.tell()
    buf.seek(0)

    client.put_object(
        "features",
        f"{run_id}/featured_dataset.parquet",
        buf,
        size,
    )
    logger.info(
        "Uploaded features/%s/featured_dataset.parquet (%s bytes)",
        run_id,
        f"{size:,}",
    )


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    conn = get_pg_conn()
    df = _load_data(conn)
    conn.close()

    df = _compute_features(df)
    df = _clean_and_sample(df)

    df_out = df.select(FEATURE_COLS)
    logger.info(
        "Feature matrix: %s rows × %s cols", f"{len(df_out):,}", len(df_out.columns)
    )
    logger.info("Features: %s", FEATURE_COLS)

    _upload_to_minio(run_id, df_out)
