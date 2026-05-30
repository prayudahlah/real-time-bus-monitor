# Real-Time Bus Monitor

Prediksi ETA bus WMATA Washington DC — pipeline batch training + real-time inference terdistribusi di dua laptop via Tailscale.

## Arsitektur (3 Fase)

```
PHASE 1: BATCH (laptop batch, standalone)
┌─────────────────────────────────────────┐
│ PostgreSQL ← data statis + metadata     │
│ MinIO ← data lake + model artifacts     │
│ MLflow ← model registry                 │
│ Airflow ← orchestrator DAG              │
│  extract → transform → train → load     │
└─────────────────────────────────────────┘

PHASE 2: STREAM (laptop stream, standalone)
┌─────────────────────────────────────────┐
│ ZooKeeper + Kafka ← event bus           │
│ PostgreSQL ← data sink                  │
│ FastAPI ← inference service             │
│ (WMATA Fetcher, Dashboard — nanti)      │
└─────────────────────────────────────────┘

PHASE 3: CDC (integrasi, nanti)
Batch → Debezium Connect → Kafka (stream) → CDC Consumer → PostgreSQL stream
```

## Prasyarat

- **Docker** + **Docker Compose** plugin (v2.20+)
- **Tailscale** terinstall dan kedua laptop dalam satu network
- Git

## Setup Awal

### 1. Clone repository (di kedua laptop)

```bash
git clone git@github.com:prayudahlah/real-time-bus-monitor.git
cd real-time-bus-monitor
```

### 2. Setup environment variables

**Laptop Batch:**

```bash
cp batch/.env.example batch/.env
# Isi: POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD
```

**Laptop Stream:**

```bash
cp stream/.env.example stream/.env
# Isi: STREAM_TAILSCALE_IP untuk Kafka advertised listener, POSTGRES_PASSWORD
```

### 3. Start services

Kedua laptop bisa di-start **independen** — tidak ada dependensi satu sama lain di fase ini.

**Laptop Batch:**

```bash
cd batch
docker compose up -d
```

**Laptop Stream:**

```bash
cd stream
docker compose up -d zookeeper kafka postgres-stream inference
```

### 4. Verifikasi

| Service | URL | Laptop |
|---|---|---|
| MinIO Console | `http://{BATCH_IP}:9001` | Batch |
| MLflow UI | `http://{BATCH_IP}:5000` | Batch |
| Airflow Webserver | `http://{BATCH_IP}:8080` | Batch |
| FastAPI Inference | `http://{STREAM_IP}:8000/health` | Stream |

## Panduan Development per Fase

### Phase 1: Batch Pipeline

Service yang berjalan terus-menerus:
- PostgreSQL, MinIO, MLflow, Airflow (webserver + scheduler)

Service yang dipanggil oleh Airflow DAG (bukan long-running):
- Extract, Transform, Train, Load (masing-masing di `batch/services/`)

**Menjalankan pipeline (trigger DAG):**
1. Buka Airflow UI di `http://{BATCH_IP}:8080` (user: `admin`, pass: `admin`)
2. Aktifkan DAG `batch_pipeline`
3. Trigger manual

Atau via CLI:

```bash
docker exec batch-airflow-scheduler airflow dags trigger batch_pipeline
```

**Airflow DAG tasks:**
```
extract → transform → train → register_mlflow → load_postgres
```

### Phase 2: Stream Services

Service yang berjalan terus-menerus:
- ZooKeeper, Kafka, PostgreSQL, FastAPI Inference

Service yang belum aktif (pakai `profiles: [nanti]`):
- WMATA Fetcher, Dashboard

**Untuk mengaktifkan service yang ditunda:**

```bash
docker compose --profile nanti up -d
```

**FastAPI endpoint:**
- `GET /health` — status service + model loaded
- `POST /predict` — prediksi ETA (body: bus_id, lat, lon, speed, route_id)

### Phase 3: CDC Integration (nanti)

Akan menambahkan:
- **Batch:** Debezium Connect + init Connector
- **Stream:** CDC Consumer → sync data statis dari PostgreSQL batch ke stream

## Network Antar Laptop

Kedua laptop terhubung via **Tailscale** (MagicDNS).

### Konfigurasi koneksi:

| Arah | Tujuan | Port | Fase |
|---|---|---|---|
| Stream → Batch | MLflow Tracking API | 5000 | Phase 2 |
| Batch → Stream | Kafka bootstrap server | 9092 | Phase 3 |

Pastikan firewall di kedua laptop mengizinkan traffic Docker ke port-port tersebut.

## Catatan Penting

1. **Startup:** Kedua laptop bisa di-start parallel — tidak ada dependensi antar laptop di Phase 1 & 2.

2. **Phase 3 (CDC) nanti membutuhkan:**
   - Kafka di stream laptop sudah berjalan
   - Debezium Connect di batch akan connect ke Kafka stream

3. **First-time setup batch:**
   - Trigger Airflow DAG sekali manual untuk training model pertama
   - MLflow UI: set model stage ke `Production`

4. **Hardware requirements:**
   - Batch: minimal 8 GB RAM (16 GB recommended untuk transform + train)
   - Stream: minimal 4 GB RAM (8 GB recommended)
