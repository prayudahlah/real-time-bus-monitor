import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_stops_to_postgis import main


def test_load_stops_to_postgis(mocker, mock_minio, mock_postgis):
    df = pl.DataFrame(
        {
            "stop_id": [101, 102],
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

    conn, cur = mock_postgis
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    assert cur.execute.call_count == 3
    conn.commit.assert_called_once()
