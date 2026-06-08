CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_code TEXT,
    stop_name TEXT,
    geom GEOMETRY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS idx_stops_geom ON stops USING GIST (geom);

CREATE TABLE IF NOT EXISTS route_paths (
    shape_id TEXT PRIMARY KEY,
    geom GEOMETRY(LINESTRING, 4326)
);

CREATE INDEX IF NOT EXISTS idx_route_paths_geom ON route_paths USING GIST (geom);
