import io
import logging
import os
import zipfile
from datetime import datetime

import polars as pl
import requests
from tasks.utils import get_minio_client

logger = logging.getLogger(__name__)


def main(**kwargs):
    api_key = os.environ["WMATA_API_KEY"]

    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    logger.info("RUN_ID=%s", run_id)

    resp = requests.get(
        "https://api.wmata.com/gtfs/bus-gtfs-static.zip",
        headers={"api_key": api_key},
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    last_quarter = -1
    chunks = []
    for chunk in resp.iter_content(chunk_size=8192):
        chunks.append(chunk)
        downloaded += len(chunk)
        pct = downloaded * 100 // total if total else 0
        quarter = pct // 25
        if quarter != last_quarter:
            logger.info(
                "Downloading... %s / %s bytes (%s%%)",
                f"{downloaded:,}",
                f"{total:,}",
                pct,
            )
            last_quarter = quarter

    zip_bytes = b"".join(chunks)
    logger.info("Downloaded %s bytes", f"{len(zip_bytes):,}")

    client = get_minio_client()

    zip_path = f"{run_id}/bus-gtfs-static.zip"
    client.put_object(
        "raw-data",
        zip_path,
        io.BytesIO(zip_bytes),
        len(zip_bytes),
    )
    logger.info("Uploaded ZIP → raw-data/%s", zip_path)

    files = ["routes.txt", "stops.txt", "trips.txt", "stop_times.txt"]
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for fname in files:
            if fname not in zf.namelist():
                logger.warning("%s not found in ZIP", fname)
                continue

            df = pl.read_csv(zf.open(fname), try_parse_dates=False)
            buf = io.BytesIO()
            df.write_parquet(buf)
            size = buf.tell()
            buf.seek(0)

            parquet_name = fname.replace(".txt", ".parquet")
            obj_path = f"{run_id}/{parquet_name}"
            client.put_object(
                "raw-data",
                obj_path,
                buf,
                size,
            )
            logger.info(
                "Uploaded %s (%s rows) → raw-data/%s",
                parquet_name,
                f"{len(df):,}",
                obj_path,
            )

    logger.info("Extract complete")
    return run_id


if __name__ == "__main__":
    import sys

    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
