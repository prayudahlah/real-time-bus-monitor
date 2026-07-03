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
| **Batch Pipeline** | `batch/` | Extract GTFS statis → Load ke PostgreSQL → Validasi → Feature Engineering → Training MLflow |
| **Stream Pipeline** | `stream/` | Fetch real-time vehicle positions & alerts → Kafka → Inference → Telegram Notifications |

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
| **ML Model** | LinearRegression / RandomForestRegressor (scikit-learn) |
| **API Framework** | FastAPI |
| **Protobuf (GTFS-RT)** | protobuf, gtfs-realtime-bindings |
| **Notifikasi** | Telegram Bot API |
| **Dashboard** | Streamlit |

---

## Struktur Proyek

```
real-time-bus-monitor/
│
├── assets/
│   └── architecture-diagram.gif
│
├── batch/                          # Batch pipeline
│   ├── .env.example
│   ├── compose.yaml                # Docker Compose batch services
│   ├── README.md                   # Dokumentasi batch detail
│   │
│   ├── airflow/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── dags/
│   │   │   ├── batch_pipeline_dag.py
│   │   │   └── tasks/
│   │   │       ├── extract.py
│   │   │       ├── load_routes.py
│   │   │       ├── load_stops.py
│   │   │       ├── load_trips.py
│   │   │       ├── load_stop_times.py
│   │   │       ├── validate_data.py
│   │   │       ├── feature_eng.py
│   │   │       ├── train.py
│   │   │       └── utils.py
│   │   └── plugins/
│   │
│   ├── mlflow/
│   │   └── Dockerfile
│   │
│   ├── notebooks/
│   │   └── 01-feature-eda.ipynb
│   │
│   └── postgres/init/
│       ├── 01-init-dbs.sh
│       └── 02-init-tables.sql
│
└── stream/                         # Stream pipeline
    ├── .env                        # Konfigurasi live
    ├── .env.example
    ├── compose.yaml                # Docker Compose stream services
    │
    ├── services/
    │   ├── wmata-fetcher/          # Fetch vehicle positions → Kafka
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── wmata-alerts-fetcher/   # Fetch service alerts → Kafka
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── inference/              # FastAPI: nearest stop & anomaly detection
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── alert-telegram/         # Consumer Kafka → Telegram Bot
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    │   ├── dashboard/              # Streamlit dashboard (placeholder)
    │   │   ├── app.py
    │   │   ├── Dockerfile
    │   │   └── requirements.txt
    │   │
    └── postgres/init/
        └── 01-init-tables.sql
```

---

## Batch Pipeline

### Batch Services

| Service | Container | Fungsi |
|---|---|---|
| `postgres-batch` | `batch-postgres` | Database untuk hasil cleaning & metadata Airflow/MLflow |
| `minio` | `batch-minio` | Object storage untuk raw data, features, model artifacts |
| `mlflow` | `batch-mlflow` | Model registry & experiment tracking |
| `airflow-init` | `batch-airflow-init` | Inisialisasi metadata Airflow |
| `airflow-api-server` | `batch-airflow-api-server` | Airflow webserver + REST API |
| `airflow-scheduler` | `batch-airflow-scheduler` | Scheduler DAG |
| `airflow-triggerer` | `batch-airflow-triggerer` | Triggerer untuk deferrable operators |
| `airflow-dag-processor` | `batch-airflow-dag-processor` | DAG processor |

### Alur Batch

Dijalankan setiap **Senin jam 06:00** (`0 6 * * 1`) via Airflow DAG `batch_pipeline`.

```
WMATA GTFS Static ZIP (routes.txt, stops.txt, trips.txt, stop_times.txt)
    │
    ▼
[1. Extract] ───→ raw-data/{run_id}/*.parquet (MinIO)
    │
    ▼
[2. Load to PostgreSQL] ───→ routes, stops, trips, stop_times
    │
    ▼
[3. Validate] ───→ FK checks + NULL rate checks
    │
    ▼
[4. Feature Engineering] ───→ features/{run_id}/featured_dataset.parquet (MinIO)
    │
    ▼
[5. Train] ───→ MLflow → bus_travel_time_predictor (@champion)
```

**Detail tiap tahap:**

1. **Extract** — Download GTFS static ZIP dari WMATA API, extract 4 file CSV, simpan sebagai Parquet di MinIO.
2. **Load** — Baca Parquet dari MinIO, insert ke PostgreSQL (`batch_data`) dengan foreign keys.
3. **Validate** — 3 FK checks (trip_id, route_id, stop_id) + 5 NULL rate checks. Pipeline gagal jika ada orphan atau NULL rate > 5%.
4. **Feature Engineering** — JOIN stop_times + stops, hitung jarak haversine, travel_time, hour_of_day, stop_position_pct. Filter speed<30m/s, distance<5000m. Sample max 500k rows.
5. **Train** — 5-fold CV untuk LinearRegression vs RandomForestRegressor. Champion = lower CV RMSE. Model gating: hanya promote jika lebih baik dari @champion.

### DDL PostgreSQL

**Database `batch_data`:**

```sql
routes     (route_id PK, route_short_name, route_long_name, route_type, route_color, route_text_color)
stops      (stop_id PK, stop_code, stop_name, stop_desc, stop_lat, stop_lon, zone_id, stop_url)
trips      (trip_id PK, route_id FK→routes, service_id, trip_headsign, direction_id, shape_id)
stop_times (trip_id FK→trips, arrival_time, departure_time, stop_id FK→stops, stop_sequence, pickup_type, drop_off_type)
```

**Database `airflow`** — metadata Airflow (auto-managed).
**Database `mlflow`** — metadata MLflow (auto-managed).

---

## Stream Pipeline

### Stream Services

| Service | Container | Fungsi |
|---|---|---|
| `zookeeper` | `stream-zookeeper` | Koordinator Kafka |
| `kafka` | `stream-kafka` | Message broker |
| `postgres-stream` | `stream-postgres` | Database untuk hasil inference & data referensi |
| `wmata-fetcher` | `stream-wmata-fetcher` | Fetch **vehicle positions** (tiap 30 detik) → Kafka |
| `wmata-alerts-fetcher` | `stream-wmata-alerts-fetcher` | Fetch **service alerts** (tiap 60 detik) → Kafka |
| `inference` | `stream-inference` | FastAPI: nearest stop lookup, ETA, anomaly detection |
| `alert-telegram` | `stream-alert-telegram` | Consumer Kafka: service alerts → Telegram |
| `dashboard` | `stream-dashboard` | Streamlit dashboard (placeholder) |

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
       │ inference (API)  │   │ alert-telegram     │
       │ /predict         │   │ (Kafka Consumer)   │
       │ nearest stop     │   │                    │
       │ ETA              │   │ format: HTML       │
       │ anomaly detection│   │ parse_mode         │
       └────────┬─────────┘   └─────────┬──────────┘
                │                       │
                ▼                       ▼
       PostgreSQL              Telegram Bot API
       predictions_log         → Telegram Group
```

### Kafka Topics

| Topic | Producer | Consumer | Format |
|---|---|---|---|
| `bus.raw.vehicle_positions` | `wmata-fetcher` (tiap 30s) | _tidak dikonsumsi (cadangan)_ | `{"bus_id", "lat", "lon", "speed", "route_id", "timestamp"}` |
| `bus.service.alerts` | `wmata-alerts-fetcher` (tiap 60s) | `alert-telegram` | `{"id", "header", "description", "cause", "effect", "url", "routes", "active_start", "active_end"}` |

Topics dibuat otomatis oleh Kafka (`AUTO_CREATE_TOPICS_ENABLE=true`).

---

## Telegram Alerts

Alert dikirim ke Telegram group via Bot API ketika ada **service alert** dari WMATA.

### Format Pesan

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

### Sumber Data WMATA

| Endpoint | Deskripsi | Frekuensi Fetch |
|---|---|---|
| `https://api.wmata.com/gtfs/bus-gtfsrt-alerts.pb` | GTFS-RT service alerts (Protobuf binary) | Setiap 60 detik |

### Konfigurasi Telegram

Di `stream/.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=-your_chat_id
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

**Batch:**

```bash
cp batch/.env.example batch/.env
# Isi: WMATA_API_KEY, MINIO_ROOT_PASSWORD, POSTGRES_PASSWORD, AIRFLOW_JWT_SECRET
```

**Stream:**

```bash
cp stream/.env.example stream/.env
# Isi: WMATA_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, POSTGRES_PASSWORD
```

### 3. Start Services

**Batch server:**

```bash
cd batch
docker compose up -d
```

**Stream server:**

```bash
cd stream
docker compose up -d
```

Kedua server bisa di-start independen — tidak ada dependensi satu sama lain.

### 4. Verifikasi

| Service | URL | Server |
|---|---|---|
| MinIO Console | `http://{BATCH_IP}:9001` | Batch |
| MLflow UI | `http://{BATCH_IP}:5000` | Batch |
| Airflow Webserver | `http://{BATCH_IP}:8080` | Batch |
| FastAPI Inference | `http://{STREAM_IP}:8001/health` | Stream |
| Streamlit Dashboard | `http://{STREAM_IP}:8502` | Stream |

### Port Mapping

| Service | Default Port | Env Variable |
|---|---|---|
| Kafka | 9094 | `KAFKA_PORT` |
| PostgreSQL (stream) | 5432 | `POSTGRES_PORT` |
| Inference API | 8001 | `INFERENCE_PORT` |
| Dashboard | 8502 | `DASHBOARD_PORT` |

---

## API Endpoints

### Inference Service (`http://{host}:8001`)

| Method | Path | Deskripsi |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/predict` | Prediksi nearest stop, ETA, anomaly |

**POST /predict**

Request:
```json
{
  "bus_id": "4528",
  "lat": 38.895,
  "lon": -77.036,
  "speed": 0.0,
  "route_id": "D24"
}
```

Response:
```json
{
  "bus_id": "4528",
  "nearest_stop_id": "10005",
  "distance_to_stop_m": 3278.83,
  "eta_seconds": 655.77,
  "anomaly": true,
  "anomaly_reason": "Too far from nearest stop (3279m)"
}
```

Anomaly detection logic:
- `speed > 30 m/s` → "Speed too high"
- `distance_to_stop > 500 m` → "Too far from nearest stop"

---

## Troubleshooting

### Kafka gagal start: `InconsistentClusterIdException`

Hapus volume Kafka data dan restart:

```bash
docker compose down
docker volume rm stream_kafkadata
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
docker compose logs wmata-alerts-fetcher
# Jika "WMATA_API_KEY not set", periksa stream/.env
```

### Telegram notifikasi tidak muncul

```bash
docker compose logs alert-telegram
# Pastikan: "Alert sent to Telegram" muncul
# Jika "Telegram credentials missing", periksa TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID di .env
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
docker compose logs -f alert-telegram
docker compose logs -f wmata-alerts-fetcher
```
