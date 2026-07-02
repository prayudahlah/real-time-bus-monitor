import json
import logging
import os
from threading import Event, Thread
from time import sleep, time

from flask import Flask
from minio import Minio
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"].replace("http://", "")
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)
BUCKET = "soda-reports"
DATA_SOURCES = ["batch_data", "batch_spatial"]

checks_passed = Gauge("soda_checks_passed", "Number of Soda checks passed", ["data_source"])
checks_failed = Gauge("soda_checks_failed", "Number of Soda checks failed", ["data_source"])
checks_warn = Gauge("soda_checks_warn", "Number of Soda checks with warnings", ["data_source"])
scan_ok = Gauge("soda_scan_ok", "1 if scan passed (no failures/errors), 0 otherwise", ["data_source"])
scan_timestamp = Gauge("soda_scan_timestamp_seconds", "Unix timestamp of the scan", ["data_source"])
errors_count = Gauge("soda_errors_count", "Number of Soda scan errors", ["data_source"])
soda_check_result = Gauge(
    "soda_check_result",
    "Individual check result (1=pass, 0=fail, -1=warn)",
    ["data_source", "table", "check_name"],
)

app = Flask(__name__)


def find_latest_run():
    try:
        objects = list(client.list_objects(BUCKET, recursive=True))
    except Exception:
        return None
    run_ids = set()
    for obj in objects:
        parts = obj.object_name.split("/")
        if len(parts) >= 1:
            run_ids.add(parts[0])
    if not run_ids:
        return None
    return sorted(run_ids)[-1]


def update_metrics():
    run_id = find_latest_run()
    if not run_id:
        logger.warning("No soda reports found in %s", BUCKET)
        return

    for ds in DATA_SOURCES:
        key = f"{run_id}/soda_{ds}.json"
        try:
            response = client.get_object(BUCKET, key)
            data = json.loads(response.read())
            response.close()
            response.release_conn()
        except Exception as e:
            logger.warning("Could not read %s: %s", key, e)
            continue

        passed = data.get("checks_pass_count", 0)
        failed = data.get("checks_fail_count", 0)
        warn = data.get("checks_warn_count", 0)

        _checks = data.get("checks", [])

        # Fallback: count from checks array if top-level fields missing
        if passed == 0 and failed == 0 and warn == 0:
            passed = sum(1 for c in _checks if c.get("outcome") == "pass")
            failed = sum(1 for c in _checks if c.get("outcome") == "fail")
            warn = sum(1 for c in _checks if c.get("outcome") == "warn")

        has_err = data.get("hasErrors", False)
        has_fail = data.get("hasFailures", False)
        err_cnt = data.get("errors_count", 0)
        ts = data.get("scan_start", 0)

        checks_passed.labels(data_source=ds).set(passed)
        checks_failed.labels(data_source=ds).set(failed)
        checks_warn.labels(data_source=ds).set(warn)
        errors_count.labels(data_source=ds).set(err_cnt)
        scan_ok.labels(data_source=ds).set(0 if failed > 0 or has_fail or has_err else 1)
        scan_timestamp.labels(data_source=ds).set(ts if ts else time())

        for c in _checks:
            outcome = c.get("outcome")
            table = c.get("table", "unknown")
            check_name = c.get("name", "unknown")
            if outcome == "pass":
                soda_check_result.labels(data_source=ds, table=table, check_name=check_name).set(1)
            elif outcome == "fail":
                soda_check_result.labels(data_source=ds, table=table, check_name=check_name).set(0)
            else:
                soda_check_result.labels(data_source=ds, table=table, check_name=check_name).set(-1)

    logger.info("Metrics updated from run_id=%s", run_id)


def background_loop(stop_event):
    while not stop_event.is_set():
        try:
            update_metrics()
        except Exception:
            logger.exception("Error updating metrics")
        stop_event.wait(POLL_INTERVAL)


stop_event = Event()
Thread(target=background_loop, args=(stop_event,), daemon=True).start()


@app.route("/metrics")
def metrics():
    from flask import Response
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
