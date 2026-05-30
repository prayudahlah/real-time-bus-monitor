import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_stop_times import main


def test_load_stop_times(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "trip_id": ["T1", "T1"],
            "arrival_time": ["06:00:00", "06:05:00"],
            "departure_time": ["06:00:00", "06:05:00"],
            "stop_id": [101, 102],
            "stop_sequence": [1, 2],
            "pickup_type": [0, 0],
            "drop_off_type": [0, 0],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE stop_times;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
