import os
import sys
import io
from pathlib import Path

import pytest
import polars as pl
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def env_vars():
    for k, v in {
        "WMATA_API_KEY": "test_key",
        "MINIO_ENDPOINT": "http://minio:9000",
        "MINIO_ACCESS_KEY": "test",
        "MINIO_SECRET_KEY": "test123",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "gtfs",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "MLFLOW_TRACKING_URI": "http://mlflow:5000",
    }.items():
        os.environ.setdefault(k, v)


def make_parquet_bytes(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


@pytest.fixture
def mock_minio(mocker):
    client = MagicMock()
    for mod in ["load_routes", "load_stops", "load_trips", "load_stop_times"]:
        mocker.patch(f"tasks.{mod}.get_minio_client", return_value=client)
    return client


@pytest.fixture
def mock_postgres(mocker):
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    for mod in ["load_routes", "load_stops", "load_trips", "load_stop_times"]:
        mocker.patch(f"tasks.{mod}.get_pg_conn", return_value=conn)
    return conn, cur
