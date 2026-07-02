import io
import logging
import os

import mlflow
import mlflow.sklearn
from mlflow import register_model, MlflowClient
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature
import numpy as np
import polars as pl
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split, cross_validate
from tasks.utils import get_minio_client

logger = logging.getLogger(__name__)

logging.getLogger("mlflow.sklearn").setLevel(logging.ERROR)
logging.getLogger("mlflow.tracking._model_registry.fluent").setLevel(logging.ERROR)

FEATURE_COLS = [
    "distance_to_next_m",
    "stop_sequence",
    "hour_of_day",
    "stop_position_pct",
]
TARGET = "travel_time_sec"
CLEANING_SPEED_MAX = 30
CLEANING_DISTANCE_MAX = 5000
CV_FOLDS = 5
RANDOM_STATE = 42


def _run_cv(model, X_train, y_train):
    scores = cross_validate(
        model,
        X_train,
        y_train,
        cv=CV_FOLDS,
        scoring={
            "mae": "neg_mean_absolute_error",
            "rmse": "neg_root_mean_squared_error",
            "r2": "r2",
        },
        return_train_score=False,
    )
    return {
        "mae": -scores["test_mae"].mean(),
        "rmse": -scores["test_rmse"].mean(),
        "r2": scores["test_r2"].mean(),
        "mae_std": scores["test_mae"].std(),
        "rmse_std": scores["test_rmse"].std(),
        "r2_std": scores["test_r2"].std(),
    }


def _log_to_mlflow(
    run_id,
    cv_results,
    best_name,
    best_cv,
    champion,
    X_train,
    y_pred_train,
    mae,
    rmse,
    r2,
):
    signature = infer_signature(X_train, y_pred_train)

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    with mlflow.start_run(run_name=f"batch_{run_id}") as active_run:
        mlflow.set_tags(
            {
                "task": "regression",
                "framework": "scikit-learn",
                "target": TARGET,
                "model_type": best_name,
                "feature_count": str(len(FEATURE_COLS)),
                "cv_folds": str(CV_FOLDS),
            }
        )

        params = {
            "feature_columns": str(FEATURE_COLS),
            "target": TARGET,
            "cleaning_speed_max_mps": CLEANING_SPEED_MAX,
            "cleaning_distance_max_m": CLEANING_DISTANCE_MAX,
            "model_type": best_name,
            "cv_folds": CV_FOLDS,
            "pipeline_run_id": run_id,
        }
        if best_name == "RandomForest":
            params["rf_n_estimators"] = 100
            params["rf_max_depth"] = 10
            params["rf_min_samples_leaf"] = 5
        mlflow.log_params(params)

        for name, scores in cv_results.items():
            prefix = "lr" if name == "LinearRegression" else "rf"
            mlflow.log_metrics(
                {
                    f"{prefix}_cv_mae": round(scores["mae"], 2),
                    f"{prefix}_cv_rmse": round(scores["rmse"], 2),
                    f"{prefix}_cv_r2": round(scores["r2"], 4),
                    f"{prefix}_cv_mae_std": round(scores["mae_std"], 2),
                    f"{prefix}_cv_rmse_std": round(scores["rmse_std"], 2),
                    f"{prefix}_cv_r2_std": round(scores["r2_std"], 4),
                }
            )

        mlflow.log_metrics(
            {
                "test_mae_seconds": round(mae, 2),
                "test_rmse_seconds": round(rmse, 2),
                "test_r2": round(r2, 4),
            }
        )

        mlflow.sklearn.log_model(champion, name="model", signature=signature)

        mlflow_run_id = active_run.info.run_id
        logger.info("MLflow run_id=%s", mlflow_run_id)

        mv = register_model(
            model_uri=f"runs:/{mlflow_run_id}/model",
            name="bus_travel_time_predictor",
        )
        new_version = mv.version

        mlc = MlflowClient()
        mlc.update_registered_model(
            name="bus_travel_time_predictor",
            description=(
                f"Champion: {best_name} (CV RMSE={best_cv['rmse']:.2f}, "
                f"Test R²={r2:.3f})\n"
                f"Features: {FEATURE_COLS}\n"
                f"Pipeline run: {run_id}"
            ),
        )

        # ---- Model gating: compare vs champion alias ----
        champion_rmse = None
        try:
            champ_mv = mlc.get_model_version_by_alias(
                "bus_travel_time_predictor", "champion"
            )
            champ_run = mlc.get_run(champ_mv.run_id)
            champion_rmse = champ_run.data.metrics.get("test_rmse_seconds")
        except MlflowException:
            pass

        if champion_rmse is None:
            mlc.set_registered_model_alias(
                "bus_travel_time_predictor", "champion", new_version
            )
            logger.info(
                "No existing champion → @champion set on version %s", new_version
            )
        elif rmse < champion_rmse:
            mlc.set_registered_model_alias(
                "bus_travel_time_predictor", "champion", new_version
            )
            logger.info(
                "@champion moved to version %s (RMSE=%.2f < previous %.2f)",
                new_version,
                rmse,
                champion_rmse,
            )
        else:
            logger.warning(
                "Champion NOT promoted — RMSE=%.2f >= @champion RMSE=%.2f",
                rmse,
                champion_rmse,
            )

        logger.info(
            "Registered model bus_travel_time_predictor (run_id=%s)",
            mlflow_run_id,
        )

    return mlflow_run_id


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")

    client = get_minio_client()

    logger.info("Reading featured_dataset.parquet from MinIO...")
    response = client.get_object("features", f"{run_id}/featured_dataset.parquet")
    buf = io.BytesIO(response.read())
    df = pl.read_parquet(buf)
    logger.info(
        "Loaded %s rows from features/%s/featured_dataset.parquet",
        f"{len(df):,}",
        run_id,
    )

    X = df.select(FEATURE_COLS).to_numpy()
    y = df[TARGET].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE
    )

    models = {
        "LinearRegression": LinearRegression(),
        "RandomForest": RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_leaf=5,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
    }

    cv_results = {}
    for name, model in models.items():
        logger.info("Running %d-fold CV for %s...", CV_FOLDS, name)
        cv_results[name] = _run_cv(model, X_train, y_train)
        logger.info(
            "%s CV: R² = %.4f ± %.4f, MAE = %.2f ± %.2f, RMSE = %.2f ± %.2f",
            name,
            cv_results[name]["r2"],
            cv_results[name]["r2_std"],
            cv_results[name]["mae"],
            cv_results[name]["mae_std"],
            cv_results[name]["rmse"],
            cv_results[name]["rmse_std"],
        )

    best_name = min(cv_results, key=lambda n: cv_results[n]["rmse"])
    best_cv = cv_results[best_name]
    logger.info("Champion model: %s (CV RMSE = %.2f)", best_name, best_cv["rmse"])

    champion = models[best_name]
    champion.fit(X_train, y_train)

    y_pred_train = champion.predict(X_train)

    y_pred = champion.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    logger.info("Test: R² = %.3f, MAE = %.1fs, RMSE = %.1fs", r2, mae, rmse)
    if best_name == "LinearRegression":
        logger.info(
            "Formula: travel_time = %.2f + (%.4f × distance) + (%.4f × stop_seq)",
            champion.intercept_,
            champion.coef_[0],
            champion.coef_[1],
        )

    return _log_to_mlflow(
        run_id,
        cv_results,
        best_name,
        best_cv,
        champion,
        X_train,
        y_pred_train,
        mae,
        rmse,
        r2,
    )

