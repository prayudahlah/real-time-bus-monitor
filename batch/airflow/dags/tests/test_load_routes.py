import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_routes import main


def test_load_routes(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "route_id": ["R1", "R2"],
            "route_short_name": ["10A", "20B"],
            "route_long_name": ["Route 10A", "Route 20B"],
            "route_type": [3, 3],
            "route_color": ["FF0000", "00FF00"],
            "route_text_color": ["FFFFFF", "000000"],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE routes CASCADE;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
