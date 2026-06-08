import polars as pl
from unittest.mock import MagicMock
from tests.conftest import make_parquet_bytes
from tasks.load_shapes_to_postgis import main


def test_load_shapes_to_postgis(mocker, mock_minio, mock_postgis):
    df = pl.DataFrame(
        {
            "shape_id": ["S1", "S1", "S2", "S2"],
            "shape_pt_lat": [38.9, 38.91, 38.92, 38.93],
            "shape_pt_lon": [-77.0, -77.01, -77.02, -77.03],
            "shape_pt_sequence": [1, 2, 1, 2],
        }
    )
    mock_minio.get_object.return_value.read.return_value = make_parquet_bytes(df)

    conn, cur = mock_postgis
    ti = MagicMock()
    ti.xcom_pull.return_value = "run_20260530_000000"

    main(ti=ti)

    assert cur.execute.call_count == 3
    conn.commit.assert_called_once()
