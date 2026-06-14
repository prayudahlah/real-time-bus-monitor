-- ============================================
-- Tabel routes (sama dengan batch)
-- ============================================
CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name TEXT,
    route_type INTEGER,
    route_color TEXT,
    route_text_color TEXT
);

-- ============================================
-- Tabel stops (sama dengan batch)
-- ============================================
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

-- ============================================
-- Tabel trips (sama dengan batch)
-- ============================================
CREATE TABLE IF NOT EXISTS trips (
    route_id TEXT REFERENCES routes(route_id),
    service_id TEXT,
    trip_id TEXT PRIMARY KEY,
    trip_headsign TEXT,
    direction_id INTEGER,
    shape_id TEXT
);

-- ============================================
-- Tabel stop_times (sama dengan batch)
-- ============================================
CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT REFERENCES trips(trip_id),
    arrival_time TEXT,
    departure_time TEXT,
    stop_id TEXT REFERENCES stops(stop_id),
    stop_sequence INTEGER,
    pickup_type INTEGER,
    drop_off_type INTEGER
);

-- ============================================
-- Index (sama dengan batch)
-- ============================================
CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id ON stop_times(trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id ON stop_times(stop_id);
CREATE INDEX IF NOT EXISTS idx_trips_route_id ON trips(route_id);

-- ============================================
-- Untuk CDC (replica identity full) jika nanti diaktifkan
-- ============================================
ALTER TABLE routes REPLICA IDENTITY FULL;
ALTER TABLE stops REPLICA IDENTITY FULL;
ALTER TABLE trips REPLICA IDENTITY FULL;
ALTER TABLE stop_times REPLICA IDENTITY FULL;

-- ============================================
-- Tabel tambahan untuk logging prediksi (digunakan inference service)
-- ============================================
CREATE TABLE IF NOT EXISTS predictions_log (
    id SERIAL PRIMARY KEY,
    bus_id TEXT,
    nearest_stop_id TEXT,
    distance_m DOUBLE PRECISION,
    eta_sec DOUBLE PRECISION,
    anomaly BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Tabel logging prediksi ML (inference-ml service)
-- ============================================
CREATE TABLE IF NOT EXISTS predictions_ml_log (
    id SERIAL PRIMARY KEY,
    bus_id TEXT,
    route_id TEXT,
    trip_id TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    speed DOUBLE PRECISION,
    nearest_stop_id TEXT,
    next_stop_id TEXT,
    distance_to_next_m DOUBLE PRECISION,
    stop_sequence INTEGER,
    hour_of_day INTEGER,
    stop_position_pct DOUBLE PRECISION,
    predicted_travel_time_sec DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Data contoh stops (halte bus di area Washington DC)
-- ============================================
INSERT INTO stops (stop_id, stop_name, stop_lat, stop_lon, stop_code, zone_id) VALUES
('10001', 'King St-Old Town', 38.8065, -77.0610, '10001', 'Zone1'),
('10002', 'Braddock Rd', 38.8140, -77.0512, '10002', 'Zone1'),
('10003', 'Pentagon', 38.8704, -77.0551, '10003', 'Zone2'),
('10004', 'L''Enfant Plaza', 38.8844, -77.0226, '10004', 'Zone2'),
('10005', 'Union Station', 38.8978, -77.0061, '10005', 'Zone2'),
('10006', 'Gallery Pl-Chinatown', 38.8981, -77.0216, '10006', 'Zone2'),
('10007', 'Metro Center', 38.8984, -77.0282, '10007', 'Zone2'),
('10008', 'Farragut West', 38.9014, -77.0395, '10008', 'Zone2')
ON CONFLICT (stop_id) DO NOTHING;

-- ============================================
-- Data contoh routes (beberapa rute bus WMATA)
-- ============================================
INSERT INTO routes (route_id, route_short_name, route_long_name, route_type, route_color, route_text_color) VALUES
('70', '70', 'Georgia Ave - 7th St', 3, '#000000', '#FFFFFF'),
('79', '79', 'Georgia Ave Metroextra', 3, '#000000', '#FFFFFF'),
('S2', 'S2', '16th Street', 3, '#000000', '#FFFFFF'),
('S9', 'S9', '16th Street Metroextra', 3, '#000000', '#FFFFFF')
ON CONFLICT (route_id) DO NOTHING;

-- ============================================
-- Data contoh trips (sederhana, untuk demo)
-- ============================================
INSERT INTO trips (route_id, trip_id, trip_headsign, direction_id) VALUES
('70', '70_001', 'Northbound to Silver Spring', 0),
('70', '70_002', 'Southbound to Archives', 1),
('79', '79_001', 'Northbound to Silver Spring', 0),
('S2', 'S2_001', 'Northbound to Silver Spring', 0)
ON CONFLICT (trip_id) DO NOTHING;

-- ============================================
-- Data contoh stop_times (hubungan trip dengan stop)
-- ============================================
INSERT INTO stop_times (trip_id, arrival_time, departure_time, stop_id, stop_sequence) VALUES
('70_001', '06:00:00', '06:00:00', '10007', 1),
('70_001', '06:05:00', '06:05:00', '10008', 2),
('70_001', '06:15:00', '06:15:00', '10005', 3)
ON CONFLICT DO NOTHING;