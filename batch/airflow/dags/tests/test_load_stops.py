import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_stops import main


def test_load_stops(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "stop_id": [1, 2],
            "stop_code": [100, 200],
            "stop_name": ["A St", "B Ave"],
            "stop_desc": [None, None],
            "stop_lat": [38.9, 38.91],
            "stop_lon": [-77.0, -77.01],
            "zone_id": [None, None],
            "stop_url": [None, None],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE stops CASCADE;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
