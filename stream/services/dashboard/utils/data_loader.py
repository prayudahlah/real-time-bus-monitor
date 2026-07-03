import os
import time
import logging
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TRINO_HOST = os.getenv("TRINO_HOST", "localhost")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
CATALOG = "postgres"
SCHEMA = "public"

PG_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres-stream"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "dbname": os.getenv("POSTGRES_DB", "stream_data"),
}

BATCH_CATALOG = "batch_pg"
POSTGIS_CATALOG = "postgis"


def _trino_query(sql):
    from trino.dbapi import connect
    conn = connect(host=TRINO_HOST, port=TRINO_PORT, user="dashboard")
    cur = conn.cursor()
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description] if cur.description else []
    rows = cur.fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=cols)


def _pg_query(sql):
    import psycopg2
    conn = psycopg2.connect(**PG_CONFIG)
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def _try_query(sql, use_batch=False, use_spatial=False):
    if use_spatial:
        try:
            return _trino_query(sql)
        except Exception:
            pass
        return None
    catalog = BATCH_CATALOG if use_batch else CATALOG
    try:
        return _trino_query(sql.format(catalog=catalog))
    except Exception:
        pass
    try:
        pg_sql = sql.replace("{catalog}.", "")
        return _pg_query(pg_sql)
    except Exception:
        pass
    return None


# ─── Mock data generators (time-seeded for realistic demo) ────────────

MOCK_ROUTE_NAMES = {
    "70": "Georgia Ave - 7th St",
    "79": "Georgia Ave Metroextra",
    "S2": "16th Street",
    "S9": "16th Street Metroextra",
    "D6": "Sibley Hospital - Stadium-Armory",
    "32": "Pennsylvania Avenue",
    "52": "14th Street",
    "H1": "Brookland - Potomac Park",
}

# Seed changes every 15s so data shifts but stays stable within cache window
def _rng():
    return np.random.default_rng(int(time.time() // 15))


def _mock_bus_positions():
    rng = _rng()
    now = datetime.now()
    routes = sorted(MOCK_ROUTE_NAMES.keys())
    rows = []
    for i in range(40):
        bus_id = f"BUS_{1000 + i}"
        route_id = routes[i % len(routes)]
        age = rng.uniform(0, 600)
        status = "Live" if age < 60 else ("Tertunda" if age < 300 else "Kadaluarsa")
        rows.append({
            "bus_id": bus_id,
            "route_id": route_id,
            "lat": 38.88 + rng.uniform(-0.05, 0.05),
            "lon": -77.03 + rng.uniform(-0.04, 0.04),
            "speed": round(rng.uniform(0, 15), 1),
            "predicted_travel_time_sec": round(rng.uniform(120, 900), 1),
            "nearest_stop_id": f"STOP_{10001 + (i % 20)}",
            "next_stop_id": f"STOP_{10002 + (i % 20)}",
            "status": status,
            "created_at": now - timedelta(seconds=age),
        })
    return pd.DataFrame(rows)


def _mock_schedule():
    rows = []
    routes_data = {
        "70": [("Northbound to Silver Spring", "Metro Center", "06:00:00", "06:00:00", 1),
               ("Northbound to Silver Spring", "Farragut West", "06:05:00", "06:05:00", 2),
               ("Northbound to Silver Spring", "Union Station", "06:15:00", "06:15:00", 3),
               ("Southbound to Archives", "Union Station", "06:20:00", "06:20:00", 1),
               ("Southbound to Archives", "Farragut West", "06:30:00", "06:30:00", 2)],
        "79": [("Northbound to Silver Spring", "Pentagon", "07:00:00", "07:00:00", 1),
               ("Northbound to Silver Spring", "L'Enfant Plaza", "07:10:00", "07:10:00", 2)],
        "S2": [("Northbound to Silver Spring", "King St-Old Town", "06:30:00", "06:30:00", 1),
               ("Northbound to Silver Spring", "Braddock Rd", "06:38:00", "06:38:00", 2)],
        "S9": [("Northbound to Silver Spring", "Pentagon", "07:30:00", "07:30:00", 1)],
        "D6": [("Eastbound to Stadium-Armory", "Metro Center", "06:00:00", "06:00:00", 1),
               ("Eastbound to Stadium-Armory", "Union Station", "06:10:00", "06:10:00", 2)],
        "32": [("Eastbound to Southern Ave", "L'Enfant Plaza", "06:00:00", "06:00:00", 1),
               ("Eastbound to Southern Ave", "Pentagon", "06:12:00", "06:12:00", 2)],
        "52": [("Southbound to Anacostia", "Metro Center", "07:00:00", "07:00:00", 1)],
        "H1": [("Southbound to Potomac Park", "Brookland", "06:45:00", "06:45:00", 1)],
    }
    for route, stops in routes_data.items():
        for headsign, stop, arr, dep, seq in stops:
            rows.append({
                "route_short_name": route,
                "trip_headsign": headsign,
                "stop_name": stop,
                "arrival_time": arr,
                "departure_time": dep,
                "stop_sequence": seq,
            })
    return pd.DataFrame(rows)


def _mock_predictions():
    rng = _rng()
    now = datetime.now()
    routes = sorted(MOCK_ROUTE_NAMES.keys())
    rows = []
    base_times = {"70": 300, "79": 240, "S2": 360, "S9": 200, "D6": 450, "32": 280, "52": 310, "H1": 380}
    for i in range(200):
        route = routes[i % len(routes)]
        base = base_times.get(route, 300)
        travel_time = base * rng.uniform(0.7, 1.4)
        if travel_time < base * 0.95:
            status = "Cepat"
        elif travel_time > base * 1.05:
            status = "Lambat"
        else:
            status = "Normal"
        rows.append({
            "bus_id": f"BUS_{1000 + (i % 40)}",
            "route": route,
            "speed": round(rng.uniform(0, 15), 1),
            "next_stop_id": f"STOP_{10001 + (i % 20)}",
            "predicted_travel_time_sec": round(travel_time, 1),
            "status": status,
            "timestamp": now - timedelta(seconds=rng.uniform(0, 3600)),
        })
    return pd.DataFrame(rows)


# ─── Public loader functions (cached) ─────────────────────────────────

@st.cache_data(ttl=15, show_spinner="Memuat posisi bus...")
def load_bus_positions():
    sql = """SELECT bus_id, route_id, lat, lon, speed,
                    predicted_travel_time_sec, created_at,
                    nearest_stop_id, next_stop_id
             FROM {catalog}.public.predictions_ml_log
             ORDER BY created_at DESC LIMIT 5000"""
    df = _try_query(sql)
    if df is not None and not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        now = datetime.now()
        df["age_sec"] = (now - df["created_at"]).dt.total_seconds().clip(lower=0)
        df["status"] = df["age_sec"].apply(
            lambda x: "Live" if x < 60 else ("Tertunda" if x < 300 else "Kadaluarsa")
        )
        return df
    mock = _mock_bus_positions()
    st.info("Menggunakan data contoh — koneksi database tidak tersedia.")
    return mock


@st.cache_data(ttl=3600, show_spinner="Memuat data route...")
def load_route_descriptions():
    sql = """SELECT route_id, route_short_name, route_long_name
             FROM {catalog}.public.routes
             ORDER BY route_short_name"""
    df = _try_query(sql, use_batch=True)
    if df is None or df.empty:
        df = _try_query(sql)
    if df is not None and not df.empty:
        display = {}
        mapping = {}
        for _, row in df.iterrows():
            rid = str(row["route_id"]).strip()
            short = str(row["route_short_name"]).strip() if row["route_short_name"] else rid
            long_ = str(row["route_long_name"]).strip() if row["route_long_name"] else ""
            label = f"{short}: {long_}" if long_ else short
            display[short] = label
            mapping[rid] = label
        return display, mapping
    mock_display = {k: f"{k}: {v}" for k, v in MOCK_ROUTE_NAMES.items()}
    return mock_display, mock_display


@st.cache_data(ttl=3600, show_spinner="Memuat jadwal...")
def load_routes():
    sql = """SELECT DISTINCT route_short_name
             FROM {catalog}.public.routes
             ORDER BY route_short_name"""
    df = _try_query(sql, use_batch=True)
    if df is None or df.empty:
        df = _try_query(sql)
    if df is not None and not df.empty:
        return df["route_short_name"].dropna().unique().tolist()
    return sorted(MOCK_ROUTE_NAMES.keys())


@st.cache_data(ttl=3600, show_spinner="Memuat headsign...")
def load_headsigns(route):
    sql = """SELECT DISTINCT t.trip_headsign
             FROM {catalog}.public.trips t
             JOIN {catalog}.public.routes r ON t.route_id = r.route_id
             WHERE r.route_short_name = '{route}'
             ORDER BY t.trip_headsign""".format(route=route, catalog="{catalog}")
    df = _try_query(sql, use_batch=True)
    if df is None or df.empty:
        df = _try_query(sql)
    if df is not None and not df.empty:
        return df["trip_headsign"].dropna().unique().tolist()
    return ["Semua Arah"]


@st.cache_data(ttl=3600, show_spinner="Memuat jadwal...")
def load_schedule(route, headsign="", stop_search=""):
    where = f"r.route_short_name = '{route}'"
    if headsign and headsign != "Semua Arah":
        where += f" AND t.trip_headsign = '{headsign}'"
    if stop_search:
        where += f" AND s.stop_name ILIKE '%{stop_search}%'"
    sql = """SELECT r.route_short_name, t.trip_headsign, s.stop_name,
                    st.arrival_time, st.departure_time, st.stop_sequence
             FROM {catalog}.public.stop_times st
             JOIN {catalog}.public.trips t ON st.trip_id = t.trip_id
             JOIN {catalog}.public.routes r ON t.route_id = r.route_id
             JOIN {catalog}.public.stops s ON st.stop_id = s.stop_id
             WHERE {where}
             ORDER BY t.trip_id, st.stop_sequence
             LIMIT 5000""".format(where=where, catalog="{catalog}")
    df = _try_query(sql, use_batch=True)
    if df is None or df.empty:
        df = _try_query(sql)
    if df is not None and not df.empty:
        return df
    mock = _mock_schedule()
    if mock.empty:
        return mock
    m = mock[mock["route_short_name"] == route]
    if headsign and headsign != "Semua Arah":
        m = m[m["trip_headsign"] == headsign]
    if stop_search:
        m = m[m["stop_name"].str.contains(stop_search, case=False, na=False)]
    return m


@st.cache_data(ttl=60, show_spinner="Memuat data prediksi...")
def load_predictions():
    sql = """SELECT id, bus_id, route_id, trip_id, lat, lon, speed,
                    next_stop_id, predicted_travel_time_sec, created_at
             FROM {catalog}.public.predictions_ml_log
             ORDER BY created_at DESC LIMIT 5000"""
    df = _try_query(sql)
    if df is not None and not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df.rename(columns={"route_id": "route"}, inplace=True)
        route_avg = df.groupby("route")["predicted_travel_time_sec"].transform("mean")
        df["status"] = df.apply(
            lambda r: "Cepat" if r["predicted_travel_time_sec"] < route_avg.iloc[r.name] * 0.95
            else ("Lambat" if r["predicted_travel_time_sec"] > route_avg.iloc[r.name] * 1.05
                  else "Normal"),
            axis=1
        )
        df.rename(columns={"created_at": "timestamp"}, inplace=True)
        return df
    mock = _mock_predictions()
    st.info("Menggunakan data contoh — koneksi database tidak tersedia.")
    return mock


@st.cache_data(ttl=86400, show_spinner="Memuat data halte...")
def load_stops():
    sql = """SELECT stop_id, stop_name, ST_Y(geom) AS lat, ST_X(geom) AS lon
             FROM postgis.public.stops"""
    df = _try_query(sql, use_spatial=True)
    if df is not None and not df.empty:
        logger.info(f"Loaded {len(df):,} stops from PostGIS")
        return df
    return pd.DataFrame()


@st.cache_data(ttl=86400)
def load_stop_names():
    df = load_stops()
    if not df.empty:
        return dict(zip(df["stop_id"], df["stop_name"]))
    return {}


@st.cache_data(ttl=86400, show_spinner="Memuat jalur rute...")
def load_route_paths():
    sql = """SELECT shape_id, ST_AsText(geom) AS wkt
             FROM postgis.public.route_paths"""
    df = _try_query(sql, use_spatial=True)
    if df is not None and not df.empty:
        logger.info(f"Loaded {len(df):,} route paths from PostGIS")
        return df
    return pd.DataFrame()
