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
    stop_code TEXT,
    stop_name TEXT,
    stop_desc TEXT,
    stop_lat DOUBLE PRECISION,
    stop_lon DOUBLE PRECISION,
    zone_id TEXT,
    stop_url TEXT
);

CREATE TABLE IF NOT EXISTS trips (
    route_id TEXT REFERENCES routes(route_id),
    service_id TEXT,
    trip_id TEXT PRIMARY KEY,
    trip_headsign TEXT,
    direction_id INTEGER,
    shape_id TEXT
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT REFERENCES trips(trip_id),
    arrival_time TEXT,
    departure_time TEXT,
    stop_id TEXT REFERENCES stops(stop_id),
    stop_sequence INTEGER,
    pickup_type INTEGER,
    drop_off_type INTEGER
);

CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id ON stop_times(trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id ON stop_times(stop_id);
CREATE INDEX IF NOT EXISTS idx_trips_route_id ON trips(route_id);

CREATE TABLE IF NOT EXISTS calendar (
    service_id TEXT PRIMARY KEY,
    monday INTEGER NOT NULL,
    tuesday INTEGER NOT NULL,
    wednesday INTEGER NOT NULL,
    thursday INTEGER NOT NULL,
    friday INTEGER NOT NULL,
    saturday INTEGER NOT NULL,
    sunday INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id TEXT,
    date TEXT NOT NULL,
    exception_type INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calendar_dates_service_id ON calendar_dates(service_id);

CREATE TABLE IF NOT EXISTS agency (
    agency_id TEXT PRIMARY KEY,
    agency_name TEXT NOT NULL,
    agency_url TEXT NOT NULL,
    agency_timezone TEXT NOT NULL,
    agency_lang TEXT,
    agency_phone TEXT
);
