import os
import psycopg2

BATCH_PG = {
    "host": os.getenv("BATCH_PG_HOST", "prayudahlah"),
    "port": os.getenv("BATCH_PG_PORT", "5432"),
    "user": os.getenv("BATCH_PG_USER", "kelompok8"),
    "password": os.getenv("BATCH_PG_PASSWORD", "kelompok8"),
    "dbname": os.getenv("BATCH_PG_DB", "batch_data"),
    "connect_timeout": 30,
}

STREAM_PG = {
    "host": os.getenv("POSTGRES_HOST", "postgres-stream"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "dbname": os.getenv("POSTGRES_DB", "stream_data"),
}

TABLES = ["routes", "stops", "trips", "stop_times"]


def main():
    print("Connecting to batch-postgres (source)...")
    src = psycopg2.connect(**BATCH_PG)
    print(f"  Connected: {BATCH_PG['host']}:{BATCH_PG['port']}/{BATCH_PG['dbname']}")

    print("Connecting to stream-postgres (destination)...")
    dst = psycopg2.connect(**STREAM_PG)
    print(f"  Connected: {STREAM_PG['host']}:{STREAM_PG['port']}/{STREAM_PG['dbname']}")

    for table in TABLES:
        print(f"\nCopying {table}...")
        try:
            sc = src.cursor()
            sc.execute(f"SELECT count(*) FROM {table}")
            total = sc.fetchone()[0]
            print(f"  Source rows: {total:,}")

            dc = dst.cursor()
            dc.execute(f"TRUNCATE TABLE {table} CASCADE")
            dc.connection.commit()

            sc.execute(f"SELECT * FROM {table}")
            cols = [desc[0] for desc in sc.description]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

            batch = []
            batch_size = 5000
            copied = 0
            while True:
                rows = sc.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    dc.execute(sql, row)
                dc.connection.commit()
                copied += len(rows)
                if copied % 50000 == 0 or copied == total:
                    print(f"  Progress: {copied:,}/{total:,}")

            dc.close()
            sc.close()
            print(f"  {table}: DONE ({copied:,} rows)")
        except Exception as e:
            print(f"  ERROR: {e}")
            src.rollback()
            dst.rollback()

    src.close()
    dst.close()
    print("\nSync complete.")


if __name__ == "__main__":
    main()
