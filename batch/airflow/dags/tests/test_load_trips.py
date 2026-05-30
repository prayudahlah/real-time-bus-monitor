import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_trips import main


def test_load_trips(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "route_id": ["R1", "R1"],
            "service_id": ["WD", "WD"],
            "trip_id": ["T1", "T2"],
            "trip_headsign": ["Downtown", "Uptown"],
            "direction_id": [0, 1],
            "shape_id": ["S1", "S2"],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE trips CASCADE;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
