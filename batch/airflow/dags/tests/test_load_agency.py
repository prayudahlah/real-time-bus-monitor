import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_agency import main


def test_load_agency(mocker, mock_minio, mock_postgres):
    df = pl.DataFrame(
        {
            "agency_id": ["WMATA"],
            "agency_name": ["Washington Metropolitan Area Transit Authority"],
            "agency_url": ["https://www.wmata.com"],
            "agency_timezone": ["America/New_York"],
            "agency_lang": ["en"],
            "agency_phone": ["202-637-7000"],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgres
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    cur.execute.assert_called_once_with("TRUNCATE TABLE agency;")
    assert cur.copy_expert.called
    conn.commit.assert_called_once()
