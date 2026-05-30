from unittest.mock import MagicMock

import pytest
from airflow.exceptions import AirflowException
from tasks.validate_data import main


def _make_cursor(values):
    cur = MagicMock()
    cur.fetchone.side_effect = [(v,) for v in values]
    return cur


def _mock_pg(mocker, values):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = _make_cursor(values)
    mocker.patch("tasks.validate_data.get_pg_conn", return_value=conn)


def test_all_clean(mocker):
    _mock_pg(mocker, [0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0])
    ti = MagicMock()
    ti.xcom_pull.return_value = "test_run"
    main(ti=ti)


def test_fk_violation_fails(mocker):
    _mock_pg(mocker, [1, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0])
    ti = MagicMock()
    ti.xcom_pull.return_value = "test_run"
    with pytest.raises(AirflowException, match="stop_times.trip_id"):
        main(ti=ti)


def test_null_rate_exceeds_threshold_fails(mocker):
    _mock_pg(mocker, [0, 0, 0, 0.0, 0.12, 0.0, 0.0, 0.0])
    ti = MagicMock()
    ti.xcom_pull.return_value = "test_run"
    with pytest.raises(AirflowException, match="stop_times.departure_time"):
        main(ti=ti)
