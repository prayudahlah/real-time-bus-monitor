import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_calendar_dates import main


def test_load_calendar_dates(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "service_id": ["WD", "WD"],
            "date": ["20260101", "20260102"],
            "exception_type": [1, 2],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE calendar_dates;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
