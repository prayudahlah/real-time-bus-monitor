import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_calendar import main


def test_load_calendar(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "service_id": ["WD", "WE"],
            "monday": [1, 0],
            "tuesday": [1, 0],
            "wednesday": [1, 0],
            "thursday": [1, 0],
            "friday": [1, 0],
            "saturday": [0, 1],
            "sunday": [0, 1],
            "start_date": ["20260101", "20260101"],
            "end_date": ["20261231", "20261231"],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE calendar;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
