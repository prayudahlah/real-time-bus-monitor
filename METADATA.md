# Metadata

## batch_data (PostgreSQL)

| Table | Description | Owner | Source |
|-------|-------------|-------|--------|
| routes | Definisi rute bus (route_id, short/long name, type, color) | Kelompok 8 | WMATA GTFS Static |
| stops | Daftar halte bus dengan koordinat lat/lon | Kelompok 8 | WMATA GTFS Static |
| trips | Definisi trip per rute (route_id, service_id, direction) | Kelompok 8 | WMATA GTFS Static |
| stop_times | Jadwal kedatangan/keberangkatan per trip per stop | Kelompok 8 | WMATA GTFS Static |
| calendar | Jadwal layanan (hari aktif: Senin-Minggu) | Kelompok 8 | WMATA GTFS Static |
| calendar_dates | Pengecualian jadwal (libur, event khusus) | Kelompok 8 | WMATA GTFS Static |
| agency | Informasi agensi transit (nama, URL, timezone) | Kelompok 8 | WMATA GTFS Static |

## batch_spatial (PostGIS)

| Table | Description | Owner | Source |
|-------|-------------|-------|--------|
| stops | Halte bus dengan geometry Point (SRID 4326) | Kelompok 8 | WMATA GTFS Static |
| route_paths | Jalur rute dengan geometry LineString (SRID 4326) | Kelompok 8 | WMATA GTFS Static |

## stream_data (PostgreSQL)

| Table | Description | Owner | Source |
|-------|-------------|-------|--------|
| routes | Definisi rute bus (replica untuk real-time query) | Kelompok 8 | WMATA GTFS Static |
| stops | Daftar halte bus (replica untuk real-time query) | Kelompok 8 | WMATA GTFS Static |
| trips | Definisi trip (replica untuk real-time query) | Kelompok 8 | WMATA GTFS Static |
| stop_times | Jadwal stop times (replica untuk real-time query) | Kelompok 8 | WMATA GTFS Static |
| predictions_log | Log prediksi non-ML (bus_id, nearest_stop, distance, eta) | Kelompok 8 | inference-ml |
| predictions_ml_log | Log prediksi ML model (features + predicted_travel_time) | Kelompok 8 | inference-ml |
