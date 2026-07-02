import json
import logging
import os
from io import BytesIO
from pathlib import Path

from soda.scan import Scan

from tasks.utils import get_minio_client

logger = logging.getLogger(__name__)

SODA_DIR = Path(__file__).resolve().parent.parent / "soda"


def _run_soda_scan(name, config_file, checks_file):
    config_path = SODA_DIR / config_file
    checks_path = SODA_DIR / checks_file

    scan = Scan()
    scan.set_scan_definition_name(name)
    scan.set_data_source_name(name)
    scan.add_configuration_yaml_file(str(config_path))
    scan.add_sodacl_yaml_file(str(checks_path))
    scan.execute()

    return scan


def _upload_json(client, bucket, run_id, name, data):
    key = f"{run_id}/soda_{name}.json"
    json_bytes = json.dumps(data, indent=2).encode()
    client.put_object(
        bucket,
        key,
        BytesIO(json_bytes),
        length=len(json_bytes),
        content_type="application/json",
    )
    logger.info("Uploaded soda report to minio://%s/%s", bucket, key)


def main(**kwargs):
    ti = kwargs["ti"]
    run_id = ti.xcom_pull(task_ids="extract")
    client = get_minio_client()
    bucket = "soda-reports"

    scans = [
        ("batch_data", "configuration.yml", "checks_postgres.yml"),
        ("batch_spatial", "configuration_postgis.yml", "checks_postgis.yml"),
    ]

    all_passed = True
    for name, config_file, checks_file in scans:
        logger.info("=== Running Soda scan: %s ===", name)

        scan = _run_soda_scan(name, config_file, checks_file)

        scan_results = scan.get_scan_results()

        # Manual count from checks array (top-level counts may be missing in SDK)
        _checks = scan_results.get("checks", [])
        scan_results["checks_pass_count"] = sum(1 for c in _checks if c.get("outcome") == "pass")
        scan_results["checks_fail_count"] = sum(1 for c in _checks if c.get("outcome") == "fail")
        scan_results["checks_warn_count"] = sum(1 for c in _checks if c.get("outcome") == "warn")

        has_errors = scan_results.get("hasErrors", False)
        has_failures = scan_results.get("hasFailures", False)

        text_output = scan.get_all_checks_text()
        if text_output:
            logger.info("Soda scan results:\n%s", text_output)

        logger.info(
            "Soda scan %s: passed=%s, failed=%s, warnings=%s, errors=%s",
            name,
            scan_results["checks_pass_count"],
            scan_results["checks_fail_count"],
            scan_results["checks_warn_count"],
            scan_results.get("errors_count", 0),
        )

        _upload_json(client, bucket, run_id, name, scan_results)

        if has_errors or has_failures:
            all_passed = False

    if not all_passed:
        raise Exception("Soda scan completed with failures or errors")
