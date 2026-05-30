# Batch Pipeline — WMATA DC Real-Time Bus Monitor

## Pipeline Overview

Batch pipeline orchestrated via **Airflow** (`batch_pipeline` DAG), menjalankan 5 langkah setiap **Senin jam 06:00** (`0 6 * * 1`).

```
WMATA GTFS Static API
    │
    ▼ [1. Extract]
raw-data/{run_id}/*.parquet (MinIO)
    │
    ▼ [2. Load to PostgreSQL]
routes ──→ trips ──→ stop_times
stops   ────────────→ stop_times
    │
    ▼ [3. Validate]
FK checks (3) + NULL rate checks (5)
    │
    ▼ [4. Feature Engineering]
features/{run_id}/featured_dataset.parquet (MinIO)
    │
    ▼ [5. Train]
MLflow → bus_travel_time_predictor (@champion)
```

---

## Data Lineage

```
┌─────────────────────────────────────────────────────────────────────┐
│  WMATA GTFS Static ZIP                                              │
│  routes.txt  stops.txt  trips.txt  stop_times.txt                   │
└──────────┬──────────────────────────────────────────────────────────┘
           │ HTTP GET + streaming
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 1 — Extract (extract.py)                                      │
│  Output: raw-data/{run_id}/*.parquet  (MinIO bucket: raw-data)     │
│  ├── routes.parquet      (6 cols, all strings)                      │
│  ├── stops.parquet       (8 cols, all strings)                      │
│  ├── trips.parquet       (6 cols, all strings)                      │
│  └── stop_times.parquet  (7 cols, all strings)                      │
└─────────────────────────────────────────────────────────────────────┘
           │ XCom: run_id
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 2 — Load to PostgreSQL (load_*.py)                            │
│  Database: batch_data                                               │
│  ├── routes     (6 cols, PK: route_id)                              │
│  ├── stops      (8 cols, PK: stop_id)                               │
│  ├── trips      (6 cols, PK: trip_id, FK: route_id → routes)       │
│  └── stop_times (7 cols, FK: trip_id → trips, stop_id → stops)     │
└─────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 3 — Validate (validate_data.py)                               │
│  Threshold: NULL rate < 5%, FK orphans = 0                          │
│  Fail → AirflowException (pipeline berhenti)                        │
└─────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 4 — Feature Engineering (feature_eng.py)                      │
│  Input: PG stop_times + stops (LEFT JOIN on stop_id)                │
│  Compute: distance haversine, travel_time, hour, position_pct       │
│  Clean: speed<30m/s, distance<5000m, travel_time>0                  │
│  Sample: max 500,000 rows                                           │
│  Output: features/{run_id}/featured_dataset.parquet  (5 cols)      │
└─────────────────────────────────────────────────────────────────────┘
           │ XCom: run_id
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 5 — Train (train.py)                                          │
│  Features (4): distance_to_next_m, stop_sequence,                   │
│                hour_of_day, stop_position_pct                       │
│  Target (1): travel_time_sec                                        │
│  Split: 80/20                                                       │
│  CV: 5-fold LinearRegression vs RandomForestRegressor               │
│  Champion: lower CV RMSE wins                                       │
│  Gating: compare vs @champion alias, promote only if better         │
│  Output: MLflow → bus_travel_time_predictor                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Step 1 — Extract

**File:** `dags/tasks/extract.py`

Download GTFS static ZIP dari WMATA API, extract 4 file teks, simpan sebagai Parquet di MinIO.

| Output (MinIO `raw-data/`) | Kolom | Sumber |
|---|---|---|
| `routes.parquet` | `route_id`, `route_short_name`, `route_long_name`, `route_type`, `route_color`, `route_text_color` | `routes.txt` |
| `stops.parquet` | `stop_id`, `stop_code`, `stop_name`, `stop_desc`, `stop_lat`, `stop_lon`, `zone_id`, `stop_url` | `stops.txt` |
| `trips.parquet` | `route_id`, `service_id`, `trip_id`, `trip_headsign`, `direction_id`, `shape_id` | `trips.txt` |
| `stop_times.parquet` | `trip_id`, `arrival_time`, `departure_time`, `stop_id`, `stop_sequence`, `pickup_type`, `drop_off_type` | `stop_times.txt` |

---

## Step 2 — Load to PostgreSQL

### Entity Relationship

```
┌──────────┐       ┌──────────┐       ┌──────────────┐
│  routes  │       │  trips   │       │  stop_times  │
├──────────┤       ├──────────┤       ├──────────────┤
│ route_id │──┐──→ │ route_id │       │ trip_id      │
│ short_name│   │   │ trip_id  │──┐──→ │ arrival_time │
│ long_name │   │   │ headsign │  │    │ departure_tm │
│ type      │   │   │ dir_id   │  │    │ stop_id      │──┐
│ color     │   │   │ shape_id │  │    │ stop_sequence│  │
│ text_color│   │   └──────────┘  │    │ pickup_type  │  │
└──────────┘   │                 │    │ drop_off_type│  │
               │                 │    └──────────────┘  │
               │                 │                      │
               │   ┌──────────┐  │                      │
               │   │  stops   │  │                      │
               │   ├──────────┤  │                      │
               └───│ stop_id  │──┘──────────────────────┘
                   │ stop_name│
                   │ stop_lat │
                   │ stop_lon │
                   └──────────┘
```

### routes

| Kolom | Tipe | Catatan |
|---|---|---|
| `route_id` | TEXT PK | |
| `route_short_name` | TEXT | Contoh: "30", "S2" |
| `route_long_name` | TEXT | Contoh: "Friendship Heights - Southern Ave" |
| `route_type` | INTEGER | GTFS: 0=tram, 1=metro, 2=rail, 3=bus |
| `route_color` | TEXT | Hex color |
| `route_text_color` | TEXT | Hex text color |

### stops

| Kolom | Tipe | Catatan |
|---|---|---|
| `stop_id` | TEXT PK | |
| `stop_code` | TEXT | |
| `stop_name` | TEXT | |
| `stop_desc` | TEXT | |
| `stop_lat` | DOUBLE PRECISION | |
| `stop_lon` | DOUBLE PRECISION | |
| `zone_id` | TEXT | |
| `stop_url` | TEXT | |

### trips

| Kolom | Tipe | Catatan |
|---|---|---|
| `route_id` | TEXT FK → routes | |
| `service_id` | TEXT | |
| `trip_id` | TEXT PK | |
| `trip_headsign` | TEXT | |
| `direction_id` | INTEGER | 0=outbound, 1=inbound |
| `shape_id` | TEXT | |

### stop_times

| Kolom | Tipe | Catatan |
|---|---|---|
| `trip_id` | TEXT FK → trips | |
| `arrival_time` | TEXT | Format HH:MM:SS (bisa > 24:00) |
| `departure_time` | TEXT | Format HH:MM:SS |
| `stop_id` | TEXT FK → stops | |
| `stop_sequence` | INTEGER | Urutan stop dalam trip |
| `pickup_type` | INTEGER | 0=regular |
| `drop_off_type` | INTEGER | 0=regular |

---

## Step 3 — Validate

**File:** `dags/tasks/validate_data.py`

### Referential Integrity (3 checks)

| Check | Query | Gagal jika |
|---|---|---|
| `stop_times.trip_id → trips.trip_id` | `LEFT JOIN ... WHERE trips.trip_id IS NULL` | > 0 orphans |
| `trips.route_id → routes.route_id` | `LEFT JOIN ... WHERE routes.route_id IS NULL` | > 0 orphans |
| `stop_times.stop_id → stops.stop_id` | `LEFT JOIN ... WHERE stops.stop_id IS NULL` | > 0 orphans |

### NULL Rate (5 checks, threshold 5%)

| Tabel | Kolom |
|---|---|
| `stop_times` | `arrival_time` |
| `stop_times` | `departure_time` |
| `stop_times` | `stop_sequence` |
| `trips` | `route_id` |
| `trips` | `service_id` |

---

## Step 4 — Feature Engineering

**File:** `dags/tasks/feature_eng.py`

### Input
`SELECT trip_id, arrival_time, stop_id, stop_sequence FROM stop_times`
`SELECT stop_id, stop_lat, stop_lon FROM stops`

### Transformasi (windowed per `trip_id`)

| Feature | Rumus |
|---|---|
| `distance_to_next_m` | `sqrt(dx² + dy²)` dengan `dx = (lon_next - lon) × 111320 × cos(lat_mid)`, `dy = (lat_next - lat) × 111320` |
| `travel_time_sec` | `arrival_next_sec - arrival_sec` |
| `hour_of_day` | `floor(arrival_sec / 3600) % 24` |
| `stop_sequence` | Dari GTFS (1-indexed) |
| `stop_position_pct` | `stop_sequence / total_stops` |

### Cleaning

| Filter | Threshold | Alasan |
|---|---|---|
| `travel_time_sec > 0` | > 0 | Travel time must be positive |
| `speed_est_mps < 30` | < 30 m/s (108 km/h) | Unrealistic speed |
| `distance_to_next_m < 5000` | < 5000 m | Unrealistic inter-stop distance |
| Sampling | ≤ 500,000 rows (seed=42) | Keep dataset manageable |

### Output (MinIO `features/`)

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `distance_to_next_m` | Float64 | Jarak antar stop (meter) |
| `stop_sequence` | Int64 | Urutan stop dalam trip |
| `hour_of_day` | Int64 | Jam kedatangan (0–23) |
| `stop_position_pct` | Float64 | Progress posisi dalam trip |
| `travel_time_sec` | Float64 | Waktu tempuh ke stop berikutnya |

---

## Step 5 — Train

**File:** `dags/tasks/train.py`

### Training Configuration

| Parameter | Value |
|---|---|
| Feature columns (X) | `distance_to_next_m`, `stop_sequence`, `hour_of_day`, `stop_position_pct` |
| Target (y) | `travel_time_sec` |
| Train/Test split | 80/20, `random_state=42` |
| CV folds | 5 |
| Models | `LinearRegression` (default), `RandomForestRegressor` (n_estimators=100, max_depth=10, min_samples_leaf=5) |

### Champion Selection

```
5-fold CV → LR rmse vs RF rmse
    ↓
Lower CV RMSE wins → fit on full training set
    ↓
Evaluate on test set → MAE, RMSE, R²
    ↓
MLflow register → bus_travel_time_predictor
    ↓
Model gating:
  ├─ No @champion alias?       → auto-set
  ├─ New RMSE < champion RMSE?  → alias pindah ke version baru
  └─ New RMSE ≥ champion RMSE?  → alias tetap, log warning
```

### MLflow Artifacts

| Entity | Detail |
|---|---|
| Registered model | `bus_travel_time_predictor` |
| Alias (replaces deprecated stages) | `@champion` |
| Model flavor | `sklearn` |
| Features logged | `feature_columns`, `target`, cleaning params, CV params |
| Metrics logged | `lr_cv_mae`, `rf_cv_mae`, `test_mae_seconds`, etc. |
| Tags | `task=regression`, `model_type=LinearRegression|RandomForest`, `cv_folds=5` |

---

## Appendix A — DDL

Eksekusi otomatis oleh `postgres/init/02-init-tables.sql`:

```sql
CREATE TABLE IF NOT EXISTS routes (
    route_id          TEXT PRIMARY KEY,
    route_short_name  TEXT,
    route_long_name   TEXT,
    route_type        INTEGER,
    route_color       TEXT,
    route_text_color  TEXT
);
ALTER TABLE routes REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS stops (
    stop_id    TEXT PRIMARY KEY,
    stop_code  TEXT,
    stop_name  TEXT,
    stop_desc  TEXT,
    stop_lat   DOUBLE PRECISION,
    stop_lon   DOUBLE PRECISION,
    zone_id    TEXT,
    stop_url   TEXT
);
ALTER TABLE stops REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS trips (
    route_id      TEXT REFERENCES routes(route_id),
    service_id    TEXT,
    trip_id       TEXT PRIMARY KEY,
    trip_headsign TEXT,
    direction_id  INTEGER,
    shape_id      TEXT
);
ALTER TABLE trips REPLICA IDENTITY FULL;

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id        TEXT REFERENCES trips(trip_id),
    arrival_time   TEXT,
    departure_time TEXT,
    stop_id        TEXT REFERENCES stops(stop_id),
    stop_sequence  INTEGER,
    pickup_type    INTEGER,
    drop_off_type  INTEGER
);
ALTER TABLE stop_times REPLICA IDENTITY FULL;

CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id ON stop_times(trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id ON stop_times(stop_id);
CREATE INDEX IF NOT EXISTS idx_trips_route_id ON trips(route_id);
```

---

## Appendix B — CDC Bridge (Debezium)

Menghubungkan batch PostgreSQL ke stream Kafka:

| Field | Value |
|---|---|
| Connector name | `batch-pg-connector` |
| Source | `postgres-batch:5432/batch_data` |
| Tables | `public.routes`, `public.stops`, `public.trips`, `public.stop_times` |
| Kafka topic prefix | `cdc` (topik: `cdc.public.routes`, dll.) |
| Decoding plugin | `pgoutput` (PG 15+) |
| Transform | `ExtractNewRecordState` (unwrap before/after) |
| Replication slot | `debezium_slot` |

Setiap **INSERT/UPDATE/DELETE** di batch PostgreSQL → otomatis dipublikasikan ke Kafka sebagai JSON payload. Ini memungkinkan stream-side application (dashboard, inference) mendapatkan data referensi terbaru secara real-time.
