import os
import io
import zipfile
import psycopg2
import requests

WMATA_API_KEY = os.getenv("WMATA_API_KEY", "2828ca53fefb4dba91eeaa9a3bdeb95d")
GTFS_URL = "https://api.wmata.com/gtfs/bus-gtfs-static.zip"

STREAM_PG = {
    "host": os.getenv("POSTGRES_HOST", "postgres-stream"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "dbname": os.getenv("POSTGRES_DB", "stream_data"),
}

FILES = [
    ("routes.txt", "routes",
     ["route_id", "route_short_name", "route_long_name", "route_type",
      "route_color", "route_text_color"]),
    ("stops.txt", "stops",
     ["stop_id", "stop_code", "stop_name", "stop_desc",
      "stop_lat", "stop_lon", "zone_id", "stop_url"]),
    ("trips.txt", "trips",
     ["route_id", "service_id", "trip_id", "trip_headsign",
      "direction_id", "shape_id"]),
    ("stop_times.txt", "stop_times",
     ["trip_id", "arrival_time", "departure_time",
      "stop_id", "stop_sequence",
      "pickup_type", "drop_off_type"]),
]


def main():
    print(f"Downloading GTFS static from WMATA...")
    resp = requests.get(GTFS_URL, headers={"api_key": WMATA_API_KEY}, timeout=120)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content):,} bytes")

    conn = psycopg2.connect(**STREAM_PG)
    print(f"  Connected to {STREAM_PG['host']}:{STREAM_PG['port']}/{STREAM_PG['dbname']}")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for txt_name, table, cols in FILES:
            if txt_name not in zf.namelist():
                print(f"  SKIP {txt_name} (not in zip)")
                continue

            print(f"Loading {table} from {txt_name}...")
            raw = zf.read(txt_name).decode("utf-8")

            cur = conn.cursor()
            cur.execute(f"TRUNCATE TABLE {table} CASCADE")

            buf = io.StringIO(raw)
            col_str = ", ".join(cols)
            cur.copy_expert(
                f"COPY {table} ({col_str}) FROM STDIN CSV HEADER",
                buf,
            )
            conn.commit()
            cur.close()

            cur = conn.cursor()
            cur.execute(f"SELECT count(*) FROM {table}")
            count = cur.fetchone()[0]
            cur.close()
            print(f"  {table}: {count:,} rows loaded")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
