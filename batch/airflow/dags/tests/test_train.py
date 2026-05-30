import polars as pl
import numpy as np
from unittest.mock import MagicMock
from mlflow.exceptions import MlflowException
from tests.conftest import make_parquet_bytes
from tasks.train import main


def _mock_cv_scores(scores_dict):
    n = len(next(iter(scores_dict.values())))
    return {
        "test_mae": -np.array(scores_dict["mae"]),
        "test_rmse": -np.array(scores_dict["rmse"]),
        "test_r2": np.array(scores_dict["r2"]),
        "fit_time": np.zeros(n),
        "score_time": np.zeros(n),
    }


def _make_df():
    return pl.DataFrame(
        {
            "distance_to_next_m": [100.0, 200.0, 300.0, 400.0, 500.0],
            "stop_sequence": [1, 2, 3, 4, 5],
            "hour_of_day": [6, 7, 8, 9, 10],
            "stop_position_pct": [0.1, 0.3, 0.5, 0.7, 0.9],
            "travel_time_sec": [60.0, 120.0, 180.0, 240.0, 300.0],
        }
    )


def _setup_mlflow_mocks(mocker, mlflow_run_id, mlc, register_version=1):
    mock_run = MagicMock()
    mock_run.info.run_id = mlflow_run_id
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_run
    mocker.patch("tasks.train.mlflow.start_run", return_value=mock_context)
    mocker.patch("tasks.train.mlflow.log_params")
    mocker.patch("tasks.train.mlflow.log_metrics")
    mocker.patch("tasks.train.mlflow.sklearn.log_model")
    mocker.patch(
        "tasks.train.register_model", return_value=MagicMock(version=register_version)
    )
    mocker.patch("tasks.train.MlflowClient", return_value=mlc)


def test_train_lr_wins(mocker):
    """LinearRegression has lower CV RMSE — should be champion."""
    df = _make_df()
    client = MagicMock()
    client.get_object.return_value.read.return_value = make_parquet_bytes(df)
    mocker.patch("tasks.train.get_minio_client", return_value=client)

    cv_lr = _mock_cv_scores(
        {
            "mae": [5.0, 5.5, 6.0],
            "rmse": [6.0, 6.5, 7.0],
            "r2": [0.98, 0.97, 0.96],
        }
    )
    cv_rf = _mock_cv_scores(
        {
            "mae": [8.0, 9.0, 10.0],
            "rmse": [10.0, 11.0, 12.0],
            "r2": [0.95, 0.94, 0.93],
        }
    )
    mocker.patch(
        "tasks.train.cross_validate",
        side_effect=[cv_lr, cv_rf],
    )

    mlc = MagicMock()
    mlc.get_model_version_by_alias.side_effect = MlflowException("no alias")
    _setup_mlflow_mocks(mocker, "test_lr_wins", mlc, register_version=5)
    log_params = mocker.patch("tasks.train.mlflow.log_params")
    log_metrics = mocker.patch("tasks.train.mlflow.log_metrics")

    ti = MagicMock()
    ti.xcom_pull.return_value = "run_lr_wins"

    result = main(ti=ti)

    assert result == "test_lr_wins"
    called_params = log_params.call_args[0][0]
    assert called_params["model_type"] == "LinearRegression"

    all_metrics = {}
    for call in log_metrics.call_args_list:
        all_metrics.update(call.args[0])

    assert "lr_cv_rmse" in all_metrics
    assert "rf_cv_rmse" in all_metrics
    assert "test_rmse_seconds" in all_metrics
    assert all_metrics["lr_cv_rmse"] < all_metrics["rf_cv_rmse"]


def test_train_rf_wins(mocker):
    """RandomForest has lower CV RMSE — should be champion."""
    df = _make_df()
    client = MagicMock()
    client.get_object.return_value.read.return_value = make_parquet_bytes(df)
    mocker.patch("tasks.train.get_minio_client", return_value=client)

    cv_lr = _mock_cv_scores(
        {
            "mae": [10.0, 11.0, 12.0],
            "rmse": [12.0, 13.0, 14.0],
            "r2": [0.80, 0.78, 0.76],
        }
    )
    cv_rf = _mock_cv_scores(
        {
            "mae": [4.0, 5.0, 6.0],
            "rmse": [5.0, 6.0, 7.0],
            "r2": [0.97, 0.96, 0.95],
        }
    )
    mocker.patch(
        "tasks.train.cross_validate",
        side_effect=[cv_lr, cv_rf],
    )

    mlc = MagicMock()
    mlc.get_model_version_by_alias.side_effect = MlflowException("no alias")
    _setup_mlflow_mocks(mocker, "test_rf_wins", mlc, register_version=6)
    log_params = mocker.patch("tasks.train.mlflow.log_params")
    log_metrics = mocker.patch("tasks.train.mlflow.log_metrics")

    ti = MagicMock()
    ti.xcom_pull.return_value = "run_rf_wins"

    result = main(ti=ti)

    assert result == "test_rf_wins"
    called_params = log_params.call_args[0][0]
    assert called_params["model_type"] == "RandomForest"
    assert called_params["rf_n_estimators"] == 100

    all_metrics = {}
    for call in log_metrics.call_args_list:
        all_metrics.update(call.args[0])

    assert all_metrics["rf_cv_rmse"] < all_metrics["lr_cv_rmse"]


# ---- Gating tests ----


def test_train_gating_first_run(mocker):
    """No @champion alias exists → auto-set."""
    df = _make_df()
    client = MagicMock()
    client.get_object.return_value.read.return_value = make_parquet_bytes(df)
    mocker.patch("tasks.train.get_minio_client", return_value=client)

    cv_lr = _mock_cv_scores(
        {"mae": [5.0, 5.5, 6.0], "rmse": [6.0, 6.5, 7.0], "r2": [0.98, 0.97, 0.96]}
    )
    cv_rf = _mock_cv_scores(
        {"mae": [8.0, 9.0, 10.0], "rmse": [10.0, 11.0, 12.0], "r2": [0.95, 0.94, 0.93]}
    )
    mocker.patch("tasks.train.cross_validate", side_effect=[cv_lr, cv_rf])

    mlc = MagicMock()
    mlc.get_model_version_by_alias.side_effect = MlflowException("no alias")
    _setup_mlflow_mocks(mocker, "gating_first", mlc, register_version=3)

    ti = MagicMock()
    ti.xcom_pull.return_value = "run_first"

    result = main(ti=ti)
    assert result == "gating_first"

    mlc.set_registered_model_alias.assert_called_once_with(
        "bus_travel_time_predictor", "champion", 3
    )


def test_train_gating_better(mocker):
    """New model beats champion → @champion moved."""
    df = _make_df()
    client = MagicMock()
    client.get_object.return_value.read.return_value = make_parquet_bytes(df)
    mocker.patch("tasks.train.get_minio_client", return_value=client)

    cv_lr = _mock_cv_scores(
        {"mae": [5.0, 5.5, 6.0], "rmse": [6.0, 6.5, 7.0], "r2": [0.98, 0.97, 0.96]}
    )
    cv_rf = _mock_cv_scores(
        {"mae": [8.0, 9.0, 10.0], "rmse": [10.0, 11.0, 12.0], "r2": [0.95, 0.94, 0.93]}
    )
    mocker.patch("tasks.train.cross_validate", side_effect=[cv_lr, cv_rf])

    champ_run = MagicMock()
    champ_run.data.metrics.get.return_value = 999.0

    mlc = MagicMock()
    mlc.get_model_version_by_alias.return_value = MagicMock(run_id="old_champ")
    mlc.get_run.return_value = champ_run
    _setup_mlflow_mocks(mocker, "gating_better", mlc, register_version=4)

    ti = MagicMock()
    ti.xcom_pull.return_value = "run_better"

    result = main(ti=ti)
    assert result == "gating_better"

    mlc.set_registered_model_alias.assert_called_once_with(
        "bus_travel_time_predictor", "champion", 4
    )


def test_train_gating_worse(mocker):
    """New model worse than champion → alias unchanged."""
    df = _make_df()
    client = MagicMock()
    client.get_object.return_value.read.return_value = make_parquet_bytes(df)
    mocker.patch("tasks.train.get_minio_client", return_value=client)

    cv_lr = _mock_cv_scores(
        {"mae": [5.0, 5.5, 6.0], "rmse": [6.0, 6.5, 7.0], "r2": [0.98, 0.97, 0.96]}
    )
    cv_rf = _mock_cv_scores(
        {"mae": [8.0, 9.0, 10.0], "rmse": [10.0, 11.0, 12.0], "r2": [0.95, 0.94, 0.93]}
    )
    mocker.patch("tasks.train.cross_validate", side_effect=[cv_lr, cv_rf])

    champ_run = MagicMock()
    champ_run.data.metrics.get.return_value = 0.0

    mlc = MagicMock()
    mlc.get_model_version_by_alias.return_value = MagicMock(run_id="old_champ")
    mlc.get_run.return_value = champ_run
    _setup_mlflow_mocks(mocker, "gating_worse", mlc, register_version=4)

    ti = MagicMock()
    ti.xcom_pull.return_value = "run_worse"

    result = main(ti=ti)
    assert result == "gating_worse"

    mlc.set_registered_model_alias.assert_not_called()
