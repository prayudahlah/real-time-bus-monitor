import os
import time
import logging
import threading
import mlflow
import mlflow.sklearn

from metrics import MODEL_LOADED

logger = logging.getLogger(__name__)

_model = None

def _load_model_async():
    global _model
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        logger.error("MLFLOW_TRACKING_URI not set")
        return
    mlflow.set_tracking_uri(tracking_uri)
    model_uri = "models:/bus_travel_time_predictor@champion"
    attempt = 0
    while True:
        attempt += 1
        try:
            logger.info(f"Loading model from {model_uri} (attempt {attempt})")
            _model = mlflow.sklearn.load_model(model_uri)
            model_type = type(_model).__name__
            MODEL_LOADED.labels(model_type=model_type).set(1)
            logger.info(f"Model loaded: {model_type}")
            break
        except Exception as e:
            logger.warning(f"Model load attempt {attempt} failed: {e}")
            if attempt % 10 == 0:
                logger.info("Retrying every 60s...")
            time.sleep(60)

def load_model():
    t = threading.Thread(target=_load_model_async, daemon=True)
    t.start()

def get_model():
    return _model
