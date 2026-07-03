# IPBD Kelompok 8 - TBP

<p align="center">
  Prayuda Afifan Handoyo | L0224008 | Kelas A<br>
  Meiva Yusnita Amalia W.K. | L0224044 | Kelas A<br>
  Infrastruktur dan Platform Big Data
</p>

# Real-Time Bus Monitor

Pipeline untuk monitoring posisi bus dan prediksi keterlambatan real-time di Washington D.C. menggunakan data WMATA (Washington Metropolitan Area Transit Authority).

## Arsitektur

![Architecture Diagram](assets/architecture-diagram.gif)

Pipeline dikembangkan dalam 2 sub-sistem independen:

| Sub-sistem | Path | Fungsi |
|---|---|---|
| **Batch Pipeline** | `batch/` | Extract GTFS statis → Load ke PostgreSQL/PostGIS → Soda DQ Check → Feature Engineering → Training MLflow |
| **Stream Pipeline** | `stream/` | Fetch real-time vehicle positions & alerts → Kafka → ML Inference → Dashboard & Telegram Notifications |

---

## Daftar Isi

- [Tech Stack](#tech-stack)
- [Struktur Proyek](#struktur-proyek)
- [Batch Pipeline](#batch-pipeline)
  - [Services](#batch-services)
  - [Alur Batch](#alur-batch)
  - [DDL PostgreSQL](#ddl-postgresql)
- [Stream Pipeline](#stream-pipeline)
  - [Services](#stream-services)
  - [Alur Stream](#alur-stream)
  - [Kafka Topics](#kafka-topics)
- [Telegram Alerts](#telegram-alerts)
- [Setup & Instalasi](#setup--instalasi)
  - [1. Clone Repository](#1-clone-repository)
  - [2. Environment Variables](#2-environment-variables)
  - [3. Start Services](#3-start-services)
  - [4. Verifikasi](#4-verifikasi)
- [API Endpoints](#api-endpoints)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Tech Stack

| Komponen | Teknologi |
|---|---|
| **Container** | Docker, Docker Compose |
| **Message Broker** | Apache Kafka + Zookeeper |
| **Stream Processing** | Python (kafka-python) |
| **Batch Orchestration** | Apache Airflow |
| **Object Storage** | MinIO |
| **ML Model Registry** | MLflow |
| **Database** | PostgreSQL 15 |
| **Spatial Database** | PostGIS 15-3.4 |
| **Federated Query** | Trino 462 |
| **Data Quality** | Soda Core |
| **ML Model** | LinearRegression / RandomForestRegressor (scikit-learn) |
| **API Framework** | FastAPI |
| **Protobuf (GTFS-RT)** | protobuf, gtfs-realtime-bindings |
| **Notifikasi** | Telegram Bot API |
| **Dashboard** | Streamlit |
| **Monitoring** | Prometheus, Grafana, cAdvisor |
| **Central Logging** | Loki + Promtail |
| **Metrics Exporter** | postgres-exporter, kafka-exporter, soda-exporter |

---

## Struktur Proyek

```
real-time-bus-monitor/
│
├── assets/
│   └── architecture-diagram.gif
│
├── compose.yaml                    # Docker Compose unified (batch + stream)
├── config/                         # Konfigurasi Trino catalogs
│
├── grafana/                        # Dashboard Grafana (JSON provisioning)
│   └── dashboards/
│       ├── infrastructure.json
│       ├── inference.json
│       ├── data_quality.json
│       └── central_logging.json
│
├── prometheus/
│   ├── prometheus.yml              # Scrape configs (6 jobs)
│   └── alert_rules.yml
│
├── batch/                          # Batch pipeline
│   ├── .env.example
│   ├── compose.yaml                # Docker Compose batch (independen)
│   ├── README.md
│   │
│   ├── airflow/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── dags/
│   │   │   ├── batch_pipeline_dag.py
│   │   │   ├── tasks/
│   │   │   │   ├── extract.py
│   │   │   │   ├── clear_tables.py
│   │   │   │   ├── load_routes.py
│   │   │   │   ├── load_stops.py
│   │   │   │   ├── load_trips.py
│   │   │   │   ├── load_stop_times.py
│   │   │   │   ├── load_calendar.py
│   │   │   │   ├── load_calendar_dates.py
│   │   │   │   ├── load_agency.py
│   │   │   │   ├── load_stops_to_postgis.py
│   │   │   │   ├── load_shapes_to_postgis.py
│   │   │   │   ├── soda_scan.py
│   │   │   │   ├── feature_eng.py
│   │   │   │   ├── train.py
│   │   │   │   └── utils.py
│   │   │   └── soda/
│   │   │       ├── checks_postgres.yml   # 41 DQ checks (batch_data)
│   │   │       └── checks_postgis.yml    # 7 DQ checks (batch_spatial)
│   │   └── plugins/
│   │
│   ├── mlflow/
│   │   └── Dockerfile
│   │
│   ├── notebooks/
│   │   └── 01-feature-eda.ipynb
│   │
│   ├── postgres/init/
│   │   ├── 01-init-dbs.sh
│   │   └── 02-init-tables.sql
│   │
│   └── postgis/init/
│       └── 01-init-spatial.sql
│
└── stream/                         # Stream pipeline
    ├── .env
    ├── .env.example
    ├── compose.yaml
    │
    ├── services/
    │   ├── wmata-fetcher/          # Fetch vehicle positions (30s) → Kafka
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── wmata-alerts-fetcher/   # Fetch service alerts (60s) → Kafka
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── inference-ml/           # FastAPI + Kafka consumer: ML prediction
    │   │   ├── app.py
    │   │   ├── preprocess.py
    │   │   ├── metrics.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── alert-telegram/         # Consumer Kafka → Telegram Bot
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── alert-proxy/            # Webhook Grafana → Telegram
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── dashboard/              # Streamlit 3 halaman
    │   │   ├── app.py
    │   │   ├── pages/
    │   │   │   ├── 1_Peta_Langsung.py
    │   │   │   ├── 2_Jadwal.py
    │   │   │   └── 3_Prediksi_Keterlambatan.py
    │   │   ├── utils/
    │   │   │   ├── data_loader.py
    │   │   │   └── styling.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── soda-exporter/          # Soda scan results → Prometheus metrics
    │   │   ├── main.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   └── trino/
    │       ├── Dockerfile
    │       └── etc/
    │           ├── config.properties
    │           └── catalog/
    │               ├── postgres.properties
    │               ├── batch_pg.properties
    │               └── postgis.properties
    │
    ├── postgres/init/
    │   └── 01-init-tables.sql
    │
    └── scripts/
        ├── sync_gtfs.py
        └── load_gtfs_static.py
```

---

## Batch Pipeline

### Batch Services

| Service | Container | Fungsi |
|---|---|---|
| `postgres-batch` | `batch-postgres` | Database relasional untuk data GTFS statis (`batch_data`) |
| `postgis-batch` | `batch-postgis` | Database spasial untuk stops (POINT) dan route_paths (LINESTRING) |
| `minio` | `batch-minio` | Object storage: raw data, features, MLflow artifacts, Soda reports |
| `minio-init` | `batch-minio-init` | Inisialisasi 4 bucket: `raw-data`, `features`, `mlflow`, `soda-reports` |
| `mlflow` | `batch-mlflow` | Model registry & experiment tracking |
| `airflow-init` | `batch-airflow-init` | Inisialisasi metadata Airflow |
| `airflow-api-server` | `batch-airflow-api-server` | Airflow webserver + REST API |
| `airflow-scheduler` | `batch-airflow-scheduler` | Scheduler DAG |
| `airflow-triggerer` | `batch-airflow-triggerer` | Triggerer untuk deferrable operators |
| `airflow-dag-processor` | `batch-airflow-dag-processor` | DAG processor |

### Alur Batch

Dijalankan setiap **Senin jam 06:00** (`0 6 * * 1`) via Airflow DAG `batch_pipeline`.

```
WMATA GTFS Static ZIP (8 file: routes, stops, trips, stop_times,
                        calendar, calendar_dates, agency, shapes)
    │
    ▼
[1. Extract] ───→ raw-data/{run_id}/*.parquet (MinIO)
    │
    ▼
[2. Clear Tables] ───→ DELETE semua tabel PostgreSQL (idempoten)
    │
    ▼
[3. Load to PostgreSQL] ───→ 7 task paralel (routes, stops, trips, stop_times,
    │                         calendar, calendar_dates, agency)
    │
    ├──────────────────────────────────────────┐
    ▼                                          ▼
[4. Load to PostGIS] ───→ 2 task paralel   [5. Soda Scan] ───→ 48 DQ checks
    stops (POINT) + route_paths (LINESTRING)    (PostgreSQL + PostGIS)
    │                                          │
    └──────────────────────────────────────────┘
                       │
                       ▼
              [6. Feature Engineering] ───→ features/{run_id}/featured_dataset.parquet
                       │
                       ▼
              [7. Train] ───→ 5-fold CV: LR vs RF → MLflow (@champion)
```

**Detail tiap tahap:**

1. **Extract** — Download GTFS static ZIP dari WMATA API, extract 8 file CSV, konversi ke Parquet via Polars, upload ke MinIO.
2. **Clear Tables** — DELETE semua baris dari 7 tabel PostgreSQL dengan urutan FK-safe agar pipeline idempoten.
3. **Load to PostgreSQL** — 7 task paralel membaca Parquet dari MinIO, TRUNCATE tabel, lalu COPY data ke PostgreSQL. Task `load_trips` menunggu `load_routes` selesai; `load_stop_times` menunggu `load_trips` dan `load_stops`.
4. **Load to PostGIS** — 2 task paralel: `load_stops_geom` memuat halte dengan geometri `ST_MakePoint(lon, lat)` SRID 4326; `load_shapes` mengagregasi titik koordinat menjadi `ST_MakeLine()` LINESTRING per `shape_id`.
5. **Soda Scan** — Menjalankan 48 data quality checks via Soda Core pada `batch_data` (41 checks) dan `batch_spatial` (7 checks). Cek mencakup row_count, missing values, duplikasi, validitas koordinat, dan referential integrity. Laporan JSON diunggah ke MinIO `soda-reports/`. Pipeline gagal jika ada check yang tidak lolos.
6. **Feature Engineering** — JOIN stop_times + stops, hitung jarak haversine (`distance_to_next_m`), `travel_time_sec`, `hour_of_day`, `stop_position_pct`. Filter: speed < 30 m/s, distance < 5000 m, travel_time > 0. Sample max 500k rows.
7. **Train** — 5-fold CV untuk LinearRegression vs RandomForestRegressor (n_estimators=100, max_depth=10). Champion = lower CV RMSE. Model gating: hanya promote jika RMSE lebih baik dari @champion saat ini.

### DDL PostgreSQL

**Database `batch_data` (PostgreSQL):**

```sql
routes     (route_id PK, route_short_name, route_long_name, route_type, route_color, route_text_color)
stops      (stop_id PK, stop_code, stop_name, stop_desc, stop_lat, stop_lon, zone_id, stop_url)
trips      (trip_id PK, route_id FK→routes, service_id, trip_headsign, direction_id, shape_id)
stop_times (trip_id FK→trips, arrival_time, departure_time, stop_id FK→stops, stop_sequence, pickup_type, drop_off_type)
calendar   (service_id PK, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
calendar_dates (service_id FK→calendar, date, exception_type)
agency     (agency_id PK, agency_name, agency_url, agency_timezone, agency_lang, agency_phone)
```

**Database `batch_spatial` (PostGIS):**

```sql
stops       (stop_id PK, geom POINT(4326) + GiST index)
route_paths (shape_id PK, geom LINESTRING(4326) + GiST index)
```

**Database `stream_data` (PostgreSQL):**

```sql
predictions_ml_log (id PK, bus_id, route_id, trip_id, lat, lon, speed,
                    nearest_stop_id, next_stop_id, distance_to_next_m,
                    stop_sequence, hour_of_day, stop_position_pct,
                    predicted_travel_time_sec, predicted_at)
```

**Database `airflow`** — metadata Airflow (auto-managed).
**Database `mlflow`** — metadata MLflow (auto-managed).

---

## Stream Pipeline

### Stream Services

| Service | Container | Port | Fungsi |
|---|---|---|---|
| `zookeeper` | `stream-zookeeper` | 2181 | Koordinator Kafka |
| `kafka` | `stream-kafka` | 9092 | Message broker |
| `postgres-stream` | `stream-postgres` | 5434 | Database stream (predictions + GTFS replica) |
| `wmata-fetcher` | `stream-wmata-fetcher` | — | Fetch vehicle positions (tiap 30s) → Kafka |
| `wmata-alerts-fetcher` | `stream-wmata-alerts-fetcher` | — | Fetch service alerts (tiap 60s) → Kafka |
| `inference-ml` | `stream-inference-ml` | 8002 | FastAPI + Kafka consumer: ML prediction |
| `alert-telegram` | `stream-alert-telegram` | — | Consumer Kafka: service alerts → Telegram |
| `alert-proxy` | `stream-alert-proxy` | 5000 | Webhook Grafana → Telegram |
| `dashboard` | `stream-dashboard` | 8501 | Streamlit 3 halaman (Peta, Jadwal, Prediksi) |
| `trino` | `stream-trino` | 8081 | Federated query engine (3 katalog) |
| `prometheus` | `batch-prometheus` | 9090 | Time-series monitoring (6 scrape jobs) |
| `grafana` | `batch-grafana` | 3000 | Dashboard + alerting (4 dashboard) |
| `cadvisor` | `batch-cadvisor` | 8082 | Container resource metrics |
| `postgres-exporter-batch` | `batch-postgres-exporter` | 9187 | PostgreSQL metrics (batch) |
| `postgres-exporter-stream` | `stream-postgres-exporter` | 9187 | PostgreSQL metrics (stream) |
| `kafka-exporter` | `stream-kafka-exporter` | 9308 | Kafka topic metrics |
| `soda-exporter` | `stream-soda-exporter` | 8003 | Data quality metrics → Prometheus |
| `loki` | `batch-loki` | 3100 | Central log aggregation (24h retention) |
| `promtail` | `batch-promtail` | 9080 | Docker log collector → Loki |

### Alur Stream

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WMATA API                                                              │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐      │
│  │ bus-gtfsrt-vehiclepos.   │    │ bus-gtfsrt-alerts.pb        │      │
│  │ (vehicle positions)      │    │ (service alerts)             │      │
│  └────────────┬─────────────┘    └──────────────┬───────────────┘      │
│               │ (tiap 30s)                      │ (tiap 60s)           │
└───────────────┼─────────────────────────────────┼──────────────────────┘
                ▼                                 ▼
       ┌─────────────────┐              ┌───────────────────┐
       │ wmata-fetcher   │              │ wmata-alerts-     │
       │                 │              │ fetcher           │
       └────────┬────────┘              └────────┬──────────┘
                │ JSON                            │ JSON
                ▼                                 ▼
       ┌──────────────────────────────────────────────┐
       │              Kafka                            │
       │  topic: bus.raw.vehicle_positions             │
       │  topic: bus.service.alerts                    │
       └──────────┬─────────────────────┬──────────────┘
                  │                     │
                  ▼                     ▼
       ┌──────────────────┐   ┌────────────────────┐
       │ inference-ml     │   │ alert-telegram     │
       │ (Kafka Consumer) │   │ (Kafka Consumer)   │
       │ nearest stop     │   │                    │
       │ feature compute  │   │ format: HTML       │
       │ ML predict       │   │ parse_mode         │
       └────────┬─────────┘   └─────────┬──────────┘
                │                       │
                ▼                       ▼
       PostgreSQL              Telegram Bot API
       predictions_ml_log      → Telegram Group (Bus Alerts)

       ┌──────────────────────────────────────────────────┐
       │  Trino (Federated Query)                         │
       │  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
       │  │ postgres   │ │ batch_pg   │ │ postgis      │ │
       │  │(stream PG) │ │(batch PG)  │ │(batch PostGIS│ │
       │  └─────┬──────┘ └─────┬──────┘ └──────┬───────┘ │
       │        └───────────────┼───────────────┘         │
       │                        ▼                         │
       │              Dashboard Streamlit                 │
       │              (Peta, Jadwal, Prediksi)            │
       └──────────────────────────────────────────────────┘
```

### Kafka Topics

| Topic | Producer | Consumer | Format |
|---|---|---|---|
| `bus.raw.vehicle_positions` | `wmata-fetcher` (tiap 30s) | `inference-ml` | `{"bus_id", "lat", "lon", "speed", "route_id", "trip_id", "start_date", "start_time", "timestamp"}` |
| `bus.service.alerts` | `wmata-alerts-fetcher` (tiap 60s) | `alert-telegram` | `{"id", "header", "description", "cause", "effect", "url", "routes", "active_start", "active_end"}` |

Topics dibuat otomatis oleh Kafka (`AUTO_CREATE_TOPICS_ENABLE=true`).

---

## Telegram Alerts

Sistem mengirimkan notifikasi otomatis ke tiga grup Telegram yang terpisah sesuai jenisnya.

### 1. Bus Alerts

Alert dikirim ke Telegram group ketika ada **service alert** dari WMATA.

#### Format Pesan

```
📢 WMATA Service Alert
D24 - Service Alert
Routes: D24
Buses will operate btwn Deanwood Station and a bus stop located on I St, NW at 13th St...
Cause: Other | Effect: Detour
More info
```

**Field detail:**

| Field | Sumber | Deskripsi |
|---|---|---|
| `header` | `alert.header_text.translation[0].text` | Judul alert (misal: "D24 - Service Alert") |
| `routes` | `alert.informed_entity[].route_id` | Daftar route ID yang terkena dampak |
| `description` | `alert.description_text.translation[0].text` | Deskripsi detail (max 400 chars) |
| `cause` | Enum → `CAUSE_MAP` | Penyebab: Construction, Police Activity, Accident, dll. |
| `effect` | Enum → `EFFECT_MAP` | Dampak: Detour, Reduced Service, Significant Delays, dll. |
| `url` | `alert.url.translation[0].text` | Link ke halaman WMATA untuk info lengkap |

**Cause mapping:**

| Code | Label |
|---|---|
| 1 | Unknown Cause |
| 2 | Other |
| 3 | Technical Problem |
| 6 | Accident |
| 8 | Weather |
| 9 | Maintenance |
| 10 | Construction |
| 11 | Police Activity |
| 12 | Medical Emergency |

**Effect mapping:**

| Code | Label |
|---|---|
| 1 | No Service |
| 2 | Reduced Service |
| 3 | Significant Delays |
| 4 | Detour |
| 6 | Modified Service |
| 8 | Stop Moved |
| 10 | Accessibility Issue |

### 2. Pipeline Alerts

Notifikasi status eksekusi task pada DAG `batch_pipeline` dari Airflow. Dikirim via callback DAG (on_success_callback / on_failure_callback) ke topic Telegram Pipeline. Mencakup status keberhasilan task, waktu run, serta tautan log untuk debugging.

### 3. Data Quality & Infrastructure Alerts

Notifikasi dari Grafana Alerting melalui `alert-proxy` (webhook receiver). Terpisah menjadi dua topic Telegram:

| Topic Telegram | Sumber | Konten |
|---|---|---|
| Infra Alerts | Grafana (CPU, RAM, disk, container down) | Alert infrastruktur |
| DQ Alerts | Grafana (hasil scan Soda) | Jumlah check passed/failed/warning + link dashboard |

### Sumber Data WMATA

| Endpoint | Deskripsi | Frekuensi Fetch |
|---|---|---|
| `https://api.wmata.com/gtfs/bus-gtfsrt-vehiclepositions.pb` | GTFS-RT vehicle positions (Protobuf binary) | Setiap 30 detik |
| `https://api.wmata.com/gtfs/bus-gtfsrt-alerts.pb` | GTFS-RT service alerts (Protobuf binary) | Setiap 60 detik |

### Konfigurasi Telegram

Di `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_BUS_TOPIC_ID=your_bus_topic_id
TELEGRAM_PIPELINE_TOPIC_ID=your_pipeline_topic_id
TELEGRAM_DQ_TOPIC_ID=your_dq_topic_id
TELEGRAM_INFRA_TOPIC_ID=your_infra_topic_id
```

---

## Setup & Instalasi

### Prerequisites

- Docker Engine 24+
- Docker Compose v2+
- WMATA API key (daftar di [WMATA Developer Portal](https://developer.wmata.com/))
- Telegram Bot Token (buat via [@BotFather](https://t.me/BotFather))

### 1. Clone Repository

```bash
git clone git@github.com:prayudahlah/real-time-bus-monitor.git
cd real-time-bus-monitor
```

### 2. Environment Variables

```bash
cp .env.example .env
# Isi: WMATA_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_*_TOPIC_ID,
#      POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, AIRFLOW_JWT_SECRET, dll.
```

### 3. Start Services

**Unified (batch + stream + monitoring):**

```bash
docker compose up -d
```

**Atau secara independen:**

```bash
cd batch && docker compose up -d    # Batch server only
cd stream && docker compose up -d   # Stream server only
```

### 4. Verifikasi

| Service | URL | Komponen |
|---|---|---|
| MinIO Console | `http://localhost:9001` | Batch |
| MLflow UI | `http://localhost:5000` | Batch |
| Airflow Webserver | `http://localhost:8080` | Batch |
| Grafana | `http://localhost:3000` | Monitoring |
| Prometheus | `http://localhost:9090` | Monitoring |
| Inference-ML | `http://localhost:8002/health` | Stream |
| Streamlit Dashboard | `http://localhost:8501` | Stream |
| Trino | `http://localhost:8081` | Stream |

### Port Mapping

| Service | Default Port | Env Variable |
|---|---|---|
| Kafka | 9092 | `KAFKA_PORT` |
| PostgreSQL (stream) | 5434 | `POSTGRES_PORT` |
| PostgreSQL (batch) | 5432 | `BATCH_PG_PORT` |
| PostGIS (batch) | 5433 | `POSTGIS_PORT` |
| Inference-ML API | 8002 | `INFERENCE_PORT` |
| Dashboard | 8501 | `DASHBOARD_PORT` |
| Trino | 8081 | `TRINO_PORT` |
| Grafana | 3000 | `GRAFANA_PORT` |
| Prometheus | 9090 | — |
| MinIO Console | 9001 | — |

---

## API Endpoints

### Inference-ML Service (`http://{host}:8002`)

| Method | Path | Deskripsi |
|---|---|---|
| GET | `/health` | Health check (status + model_loaded) |
| GET | `/metrics` | Prometheus metrics |
| POST | `/predict-ml` | Prediksi travel time dengan model ML |

**POST /predict-ml**

Request:
```json
{
  "bus_id": "4528",
  "lat": 38.895,
  "lon": -77.036,
  "speed": 5.2,
  "route_id": "D24",
  "trip_id": "12345"
}
```

Response:
```json
{
  "bus_id": "4528",
  "route_id": "D24",
  "trip_id": "12345",
  "nearest_stop_id": "10005",
  "next_stop_id": "10006",
  "distance_to_next_m": 842.5,
  "stop_sequence": 12,
  "hour_of_day": 14,
  "stop_position_pct": 0.48,
  "predicted_travel_time_sec": 187.3
}
```

**Fitur model (4 input):**

| Fitur | Tipe | Deskripsi |
|---|---|---|
| `distance_to_next_m` | Float | Jarak haversine ke halte berikutnya (meter) |
| `stop_sequence` | Int | Urutan halte dalam trip |
| `hour_of_day` | Int | Jam kedatangan (0-23) |
| `stop_position_pct` | Float | Rasio progres perjalanan (stop_sequence / total_stops) |

**Target:** `predicted_travel_time_sec` — estimasi waktu tempuh ke halte berikutnya (detik).

---

## Monitoring

Prometheus melakukan scraping metrik dari seluruh service setiap 15 detik melalui 6 scrape jobs:

| Job | Target | Port |
|---|---|---|
| `cadvisor` | cAdvisor | 8080 |
| `postgres-batch` | postgres-exporter-batch | 9187 |
| `postgres-stream` | postgres-exporter-stream | 9187 |
| `kafka` | kafka-exporter | 9308 |
| `inference-ml` | inference-ml | 8000 |
| `soda-exporter` | soda-exporter | 8000 |

### Grafana Dashboards

4 dashboard provisioned otomatis:

| Dashboard | Fokus | Data Source |
|---|---|---|
| **Infrastructure Monitoring** | CPU, RAM, disk, container, PG connections, Kafka offsets | Prometheus (cAdvisor + exporters) |
| **Inference Monitoring** | Model status, total prediksi, latency, error rate, Kafka messages | Prometheus (inference-ml metrics) |
| **Data Quality Monitoring** | Total checks, pass rate, individual check results | Prometheus (soda-exporter) |
| **Central Logging** | Log lines, errors, warnings, log rate, top error sources | Loki |

### Central Logging

Loki + Promtail mengumpulkan log dari seluruh container Docker dengan retensi 24 jam. Promtail melakukan service discovery via Docker socket dan melabeli setiap log dengan nama container.

### Grafana Alerting

Alerting terhubung ke Telegram melalui `alert-proxy` (webhook receiver). Contact point "Telegram Infra" mengirim alert ke topic Telegram yang terpisah berdasarkan kategori (infrastruktur vs data quality).

### Trino Federated Query

Trino menjembatani 3 katalog PostgreSQL sehingga dashboard Streamlit dapat mengakses data batch tanpa replikasi:

| Katalog | Target | Database |
|---|---|---|
| `postgres` | postgres-stream:5434 | `stream_data` |
| `batch_pg` | postgres-batch:5432 | `batch_data` |
| `postgis` | postgis-batch:5433 | `batch_spatial` |

---

## Troubleshooting

### Kafka gagal start: `InconsistentClusterIdException`

Hapus volume Kafka data dan restart:

```bash
docker compose down
docker volume rm real-time-bus-monitor_kafkadata
docker compose up -d
```

### Service crash: `NoBrokersAvailable`

Kafka membutuhkan waktu startup. Semua service sudah dilengkapi retry loop, tapi jika terus gagal:

```bash
# Cek log Kafka
docker compose logs kafka

# Pastikan Zookeeper healthy
docker compose ps
```

### WMATA API Key invalid

```bash
docker compose logs stream-wmata-alerts-fetcher
# Jika "WMATA_API_KEY not set", periksa .env
```

### Telegram notifikasi tidak muncul

```bash
docker compose logs stream-alert-telegram
# Pastikan: "Alert sent to Telegram" muncul
# Jika "Telegram credentials missing", periksa TELEGRAM_BOT_TOKEN di .env
```

### inference-ml model tidak load

```bash
docker compose logs stream-inference-ml
# Cek apakah MLflow sudah available
# Service akan retry setiap 60s hingga model berhasil dimuat
```

### Trino query gagal

```bash
docker compose logs stream-trino
# Pastikan 3 katalog terkoneksi: postgres, batch_pg, postgis
# Dashboard akan fallback ke direct PostgreSQL jika Trino unavailable
```

### Rebuild service setelah perubahan kode

```bash
docker compose build <service-name>
docker compose up -d <service-name>
```

Contoh: `docker compose build alert-telegram; docker compose up -d alert-telegram`

### Melihat logs

```bash
# Semua service
docker compose logs -f

# Service tertentu
docker compose logs -f stream-alert-telegram
docker compose logs -f stream-wmata-alerts-fetcher
docker compose logs -f stream-inference-ml
```
