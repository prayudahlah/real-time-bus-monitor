import polars as pl
import pytest
from unittest.mock import MagicMock
from tasks.feature_eng import main, FEATURE_COLS


def test_feature_eng(mocker):
    stop_times = pl.DataFrame(
        {
            "trip_id": ["T1"] * 3 + ["T2"] * 2,
            "arrival_time": [
                "06:00:00",
                "06:05:00",
                "06:10:00",
                "07:00:00",
                "07:03:00",
            ],
            "stop_id": [101, 102, 103, 201, 202],
            "stop_sequence": [1, 2, 3, 1, 2],
        }
    )
    stops = pl.DataFrame(
        {
            "stop_id": [101, 102, 103, 201, 202],
            "stop_lat": [38.9, 38.91, 38.92, 38.93, 38.94],
            "stop_lon": [-77.0, -77.01, -77.02, -77.03, -77.04],
        }
    )

    mocker.patch("tasks.feature_eng.pl.read_database", side_effect=[stop_times, stops])
    conn = MagicMock()
    mocker.patch("tasks.feature_eng.get_pg_conn", return_value=conn)

    client = MagicMock()
    mocker.patch("tasks.feature_eng.get_minio_client", return_value=client)

    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    assert client.put_object.called

    written_buf = client.put_object.call_args[0][2]
    written_buf.seek(0)
    result = pl.read_parquet(written_buf)
    assert set(result.columns) == set(FEATURE_COLS)
    assert len(result) == 3
    assert result["hour_of_day"].to_list() == [6, 6, 7]
    assert result["stop_position_pct"].to_list() == pytest.approx([1 / 3, 2 / 3, 1 / 2])
