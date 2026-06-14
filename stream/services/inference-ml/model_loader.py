import os
import time
import logging
import threading
import mlflow
import mlflow.sklearn

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
    for attempt in range(10):
        try:
            logger.info(f"Loading model from {model_uri} (attempt {attempt+1})")
            _model = mlflow.sklearn.load_model(model_uri)
            logger.info(f"Model loaded: {type(_model).__name__}")
            return
        except Exception as e:
            logger.warning(f"Model load attempt {attempt+1} failed: {e}")
            time.sleep(10)
    logger.error("Failed to load model after 10 attempts")

def load_model():
    t = threading.Thread(target=_load_model_async, daemon=True)
    t.start()

def get_model():
    return _model
