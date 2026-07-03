# Compliance Documentation

## 1. Data Sources

Semua data bersumber dari **WMATA API** (Washington Metropolitan Area Transit Authority):

| Data | Source | Type | Update Frequency |
|------|--------|------|------------------|
| GTFS Static | `https://api.wmata.com/gtfs/static` | Batch (ZIP) | Setiap pipeline run (scheduled + manual) |
| GTFS-RT Vehicle Positions | `https://api.wmata.com/gtfs/rt/bus-positions` | Stream (Protobuf) | Setiap 30 detik |
| GTFS-RT Service Alerts | `https://api.wmata.com/gtfs/rt/bus-alerts` | Stream (Protobuf) | Setiap 60 detik |

**Semua data adalah data publik** — tidak ada Personally Identifiable Information (PII) seperti nama, email, nomor telepon, atau alamat pribadi.

## 2. Data Security

| Aspek | Implementasi |
|-------|-------------|
| Credential storage | Semua password dan API key disimpan di file `.env` |
| Git protection | `.env` ada di `.gitignore` |
| API key | WMATA_API_KEY disimpan di environment variable |
| Bot token | TELEGRAM_BOT_TOKEN disimpan di environment variable |
| JWT secret | AIRFLOW_JWT_SECRET untuk autentikasi internal Airflow API |
| Encryption in transit | Tailscale VPN untuk komunikasi antar laptop (encrypted tunnel) |
| Encryption at rest | Database PostgreSQL tidak di-enkripsi (data publik, tidak sensitif) |

## 3. Data Quality

| Aspek | Implementasi |
|-------|-------------|
| Null checks | Soda checks: `missing_count` untuk setiap kolom kritis |
| Type validation | Soda checks: `invalid_count` untuk lat/lon range |
| Duplicate checks | Soda checks: `duplicate_count` untuk primary key |
| Row count threshold | Soda checks: `row_count > N` untuk memastikan data tidak kosong |
| Referential integrity | Validasi FK di task `validate_data.py` |
| Spatial validation | PostGIS checks: valid geometry, row count |
| Monitoring | Prometheus metrics melalui `soda-exporter` service |
| Dashboard | Grafana dashboard untuk visualisasi hasil DQ check |

### Soda Check Detail

#### batch_data

| Table | Checks | Threshold |
|-------|--------|-----------|
| stops | row_count, missing_count(stop_id, stop_name, stop_lat, stop_lon), duplicate_count(stop_id), invalid_count(stop_lat, stop_lon) | row_count > 7000 |
| routes | row_count, missing_count(route_id), duplicate_count(route_id) | row_count > 50 |
| trips | row_count, missing_count(trip_id), duplicate_count(trip_id) | row_count > 10000 |
| stop_times | row_count, missing_count(trip_id, stop_id), duplicate_count(trip_id, stop_id) | row_count > 500000 |
| calendar | row_count, missing_count(service_id), duplicate_count(service_id), invalid_count(monday-sunday) | row_count > 10 |
| calendar_dates | row_count, missing_count(service_id), invalid_count(exception_type) | row_count > 50 |
| agency | row_count, missing_count(agency_id), duplicate_count(agency_id) | row_count > 0 |

#### batch_spatial

| Table | Checks | Threshold |
|-------|--------|-----------|
| stops | row_count, missing_count(stop_id, geom), duplicate_count(stop_id) | row_count > 7000 |
| route_paths | row_count, missing_count(shape_id, geom), duplicate_count(shape_id) | row_count > 300 |

## 4. Audit Trail

| Aspek | Implementasi |
|-------|-------------|
| Pipeline execution | Airflow logs setiap task execution (DAG run_id, task_id, attempt, duration) |
| Data changes | Semua table memiliki primary key dan foreign key — perubahan data via pipeline ter-track di Airflow |
| Data quality history | Soda scan reports disimpan di MinIO (`soda-reports/`) per pipeline run |
| Prediction logs | `predictions_log` dan `predictions_ml_log` memiliki `created_at` timestamp |
| Monitoring | Prometheus metrics disimpan di database Prometheus untuk historical query |
| Infrastructure | Grafana Loki + Promtail collect semua log container |

## 5. Data Retention

| Data | Retention | Notes |
|------|-----------|-------|
| GTFS static (batch_data) | Latest run only | Pipeline overwrites existing data (reload) |
| GTFS spatial (batch_spatial) | Latest run only | Pipeline overwrites existing data (reload) |
| GTFS-RT predictions | Indefinite | Predictions accumulate; perlu monitoring disk |
| Soda scan reports (MinIO) | Per pipeline run | Disimpan per run_id |
| Airflow logs | Default (configurable) | File-based, perlu cleanup periodic |
| Prometheus metrics | Default 15d retention | Bisa dikonfigurasi |
| Loki logs | 24h retention | Konfigurasi di `config/loki-config.yml` |

## 6. PII Statement

Tidak ada **Personally Identifiable Information (PII)** yang dikumpulkan, diproses, atau disimpan dalam sistem ini. Seluruh data berasal dari WMATA API yang merupakan data transportasi publik:

- **Vehicle positions**: bus_id, lat, lon, speed, route_id, trip_id — tidak bisa diidentifikasi ke individu
- **Service alerts**: header, description, routes, cause, effect — informasi layanan publik
- **GTFS static**: stops, routes, trips, schedules — jadwal transportasi publik
- **Predictions**: bus_id, stop_id, predicted_travel_time — anonim, hanya untuk analisis perjalanan
