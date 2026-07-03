import os
import json
import logging
import time
import threading
import psycopg2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import generate_latest
from pydantic import BaseModel
from kafka import KafkaConsumer

from fastapi.responses import Response
from prometheus_client import generate_latest
from preprocess import load_gtfs_data, compute_features, set_batch_config
from model_loader import load_model, get_model
from metrics import (
    PREDICTIONS_TOTAL, ERRORS_TOTAL, LATENCY,
    KAFKA_MESSAGES, STOPS_LOADED, LAST_PREDICTION,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Inference ML")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres-stream"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "dbname": os.getenv("POSTGRES_DB", "stream_data"),
}

class PredictMLRequest(BaseModel):
    bus_id: str
    lat: float
    lon: float
    speed: float
    route_id: str
    trip_id: str = ""
    timestamp: int = 0

@app.on_event("startup")
def startup():
    logger.info("Inference-ML starting up...")
    batch_host = os.getenv("BATCH_PG_HOST")
    if batch_host:
        set_batch_config({
            "host": batch_host,
            "port": os.getenv("BATCH_PG_PORT", "5432"),
            "user": os.getenv("BATCH_PG_USER", "kelompok8"),
            "password": os.getenv("BATCH_PG_PASSWORD", "kelompok8"),
            "dbname": os.getenv("BATCH_PG_DB", "batch_data"),
            "connect_timeout": 30,
        })
        logger.info(f"Batch PG configured: {batch_host}")
    stops = load_gtfs_data(POSTGRES_CONFIG)
    STOPS_LOADED.set(stops)
    load_model()
    t = threading.Thread(target=kafka_consumer_loop, daemon=True)
    t.start()
    logger.info("Kafka consumer thread started")

def kafka_consumer_loop():
    while True:
        try:
            consumer = KafkaConsumer(
                'bus.raw.vehicle_positions',
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id='inference-ml',
                auto_offset_reset='latest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            logger.info("Connected to Kafka, consuming bus.raw.vehicle_positions")
            while True:
                records = consumer.poll(timeout_ms=1000)
                for tp, msgs in records.items():
                    for msg in msgs:
                        KAFKA_MESSAGES.inc()
                        process_bus_position(msg.value)
        except Exception as e:
            logger.warning(f"Kafka consumer error: {e}, retrying in 5s...")
            time.sleep(5)

def process_bus_position(data):
    try:
        bus_id = data.get('bus_id', 'unknown')
        lat = data.get('lat')
        lon = data.get('lon')
        speed = data.get('speed', 0)
        route_id = data.get('route_id', '')
        trip_id = data.get('trip_id', '')
        timestamp = data.get('timestamp', int(time.time()))
        if not trip_id:
            return
        if lat is None or lon is None:
            return
        model = get_model()
        if model is None:
            return
        t0 = time.time()
        result = compute_features(lat, lon, trip_id, timestamp)
        if result is None:
            return
        features, meta = result
        X = np.array([[features['distance_to_next_m'],
                        features['stop_sequence'],
                        features['hour_of_day'],
                        features['stop_position_pct']]])
        pred = float(model.predict(X)[0])
        LATENCY.observe(time.time() - t0)
        PREDICTIONS_TOTAL.labels(route_id=route_id or "unknown").inc()
        LAST_PREDICTION.set(time.time())
        _log_to_db(data, features, meta, pred)
    except Exception as e:
        ERRORS_TOTAL.labels(error_type="process").inc()
        logger.error(f"Process bus error: {e}")

def _log_to_db(data, features, meta, prediction):
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO predictions_ml_log
               (bus_id, route_id, trip_id, lat, lon, speed,
                nearest_stop_id, next_stop_id,
                distance_to_next_m, stop_sequence, hour_of_day, stop_position_pct,
                predicted_travel_time_sec)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data.get('bus_id'), data.get('route_id'), data.get('trip_id'),
             data.get('lat'), data.get('lon'), data.get('speed', 0),
             meta['current_stop_id'], meta['next_stop_id'],
             features['distance_to_next_m'], features['stop_sequence'],
             features['hour_of_day'], features['stop_position_pct'],
             round(prediction, 2))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB log failed: {e}")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": get_model() is not None,
    }

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.post("/predict-ml")
def predict_ml(req: PredictMLRequest):
    if get_model() is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    ts = req.timestamp if req.timestamp else int(time.time())
    t0 = time.time()
    result = compute_features(req.lat, req.lon, req.trip_id, ts)
    if result is None:
        raise HTTPException(status_code=400, detail="Feature computation failed")
    features, meta = result
    X = np.array([[features['distance_to_next_m'],
                    features['stop_sequence'],
                    features['hour_of_day'],
                    features['stop_position_pct']]])
    pred = float(get_model().predict(X)[0])
    LATENCY.observe(time.time() - t0)
    PREDICTIONS_TOTAL.labels(route_id=req.route_id or "unknown").inc()
    LAST_PREDICTION.set(time.time())
    return {
        "bus_id": req.bus_id,
        "route_id": req.route_id,
        "trip_id": req.trip_id,
        "features": features,
        "predicted_travel_time_sec": round(pred, 2),
        "nearest_stop_id": meta['current_stop_id'],
        "next_stop_id": meta['next_stop_id'],
    }
