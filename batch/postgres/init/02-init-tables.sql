-- Data statis dari GTFS (batch -> stream via CDC)
-- Tabel akan diisi oleh Airflow DAG (load task) dan disinkron via Debezium

CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name TEXT,
    route_type INTEGER,
    route_color TEXT,
    route_text_color TEXT
);

CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_name TEXT,
    stop_lat DOUBLE PRECISION,
    stop_lon DOUBLE PRECISION,
    wheelchair_boarding INTEGER
);

CREATE TABLE IF NOT EXISTS trips (
    route_id TEXT,
    service_id TEXT,
    trip_id TEXT PRIMARY KEY,
    trip_headsign TEXT,
    direction_id INTEGER,
    shape_id TEXT
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT,
    arrival_time TEXT,
    departure_time TEXT,
    stop_id TEXT,
    stop_sequence INTEGER,
    pickup_type INTEGER,
    drop_off_type INTEGER
);

CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id ON stop_times(trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id ON stop_times(stop_id);
CREATE INDEX IF NOT EXISTS idx_trips_route_id ON trips(route_id);

-- Wajib untuk Debezium: publish perubahan ke slot replikasi
ALTER TABLE routes REPLICA IDENTITY FULL;
ALTER TABLE stops REPLICA IDENTITY FULL;
ALTER TABLE trips REPLICA IDENTITY FULL;
ALTER TABLE stop_times REPLICA IDENTITY FULL;
