import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from geopy.distance import distance
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres-stream")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB", "stream_data")

stops_cache = []

@contextmanager
def get_db_conn():
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=POSTGRES_DB
    )
    try:
        yield conn
    finally:
        conn.close()

def load_stops():
    global stops_cache
    try:
        with get_db_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT stop_id, stop_lat, stop_lon, stop_name FROM stops")
            rows = cur.fetchall()
            stops_cache = [(r['stop_id'], r['stop_lat'], r['stop_lon'], r['stop_name']) for r in rows]
            logger.info(f"Loaded {len(stops_cache)} stops")
    except Exception as e:
        logger.error(f"Failed to load stops: {e}")

@app.on_event("startup")
def startup():
    load_stops()

@app.get("/health")
def health():
    return {"status": "ok", "service": "inference", "stops_loaded": len(stops_cache) > 0}

class PredictRequest(BaseModel):
    bus_id: str
    lat: float
    lon: float
    speed: float
    route_id: str

def find_nearest_stop(lat, lon):
    best_id = None
    best_dist = float('inf')
    for sid, slat, slon, _ in stops_cache:
        d = distance((lat, lon), (slat, slon)).meters
        if d < best_dist:
            best_dist = d
            best_id = sid
    return best_id, best_dist

@app.post("/predict")
def predict(req: PredictRequest):
    if not stops_cache:
        raise HTTPException(status_code=503, detail="Stops not loaded")
    stop_id, dist_m = find_nearest_stop(req.lat, req.lon)
    if stop_id is None:
        raise HTTPException(status_code=404, detail="No stop found")
    eta_sec = dist_m / 5.0
    reasons = []
    if req.speed > 30:
        reasons.append(f"Speed too high ({req.speed} m/s)")
    if dist_m > 500:
        reasons.append(f"Too far from nearest stop ({round(dist_m, 0)}m)")
    anomaly = len(reasons) > 0
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO predictions_log (bus_id, nearest_stop_id, distance_m, eta_sec, anomaly) VALUES (%s, %s, %s, %s, %s)",
                (req.bus_id, stop_id, dist_m, eta_sec, anomaly)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Log failed: {e}")
    return {
        "bus_id": req.bus_id,
        "nearest_stop_id": stop_id,
        "distance_to_stop_m": round(dist_m, 2),
        "eta_seconds": round(eta_sec, 2),
        "anomaly": anomaly,
        "anomaly_reason": "; ".join(reasons) if reasons else ""
    }