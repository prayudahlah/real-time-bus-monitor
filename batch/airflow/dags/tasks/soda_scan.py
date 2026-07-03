import json
import logging
import os
from io import BytesIO
from pathlib import Path

import requests
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


def _send_dq_alert(icon, status, body, passed, failed, warn):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    topic_id = os.environ.get("TELEGRAM_DQ_TOPIC_ID")
    grafana_url = os.environ.get("GRAFANA_URL", "http://localhost:3000")
    if not bot_token or not chat_id:
        logger.warning("DQ alert: Telegram credentials missing")
        return

    dashboard_url = f"{grafana_url}/d/data-quality/data-quality-monitoring"
    text = (
        f"{icon} Data Quality - {status}\n\n"
        f"{body}\n"
        f"Passed: {passed} | Failed: {failed} | Warnings: {warn}\n\n"
        f"Dashboard: <a href=\"{dashboard_url}\">Data Quality Monitoring</a>"
    )
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload,
            timeout=5,
        )
        if r.status_code != 200:
            logger.warning("DQ alert Telegram error: %s", r.text)
    except Exception as e:
        logger.warning("DQ alert failed: %s", e)


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
    all_checks = []
    total_passed = 0
    total_failed = 0
    total_warn = 0

    for name, config_file, checks_file in scans:
        logger.info("=== Running Soda scan: %s ===", name)

        scan = _run_soda_scan(name, config_file, checks_file)

        scan_results = scan.get_scan_results()

        _checks = scan_results.get("checks", [])
        scan_results["checks_pass_count"] = sum(1 for c in _checks if c.get("outcome") == "pass")
        scan_results["checks_fail_count"] = sum(1 for c in _checks if c.get("outcome") == "fail")
        scan_results["checks_warn_count"] = sum(1 for c in _checks if c.get("outcome") == "warn")

        has_errors = scan_results.get("hasErrors", False)
        has_failures = scan_results.get("hasFailures", False)

        text_output = scan.get_all_checks_text()
        if text_output:
            logger.info("Soda scan results:\n%s", text_output)

        passed = scan_results["checks_pass_count"]
        failed = scan_results["checks_fail_count"]
        warn = scan_results["checks_warn_count"]

        logger.info(
            "Soda scan %s: passed=%s, failed=%s, warnings=%s, errors=%s",
            name,
            passed,
            failed,
            warn,
            scan_results.get("errors_count", 0),
        )

        for c in _checks:
            c["data_source"] = name
            all_checks.append(c)

        total_passed += passed
        total_failed += failed
        total_warn += warn

        _upload_json(client, bucket, run_id, name, scan_results)

        if has_errors or has_failures:
            all_passed = False

    if not all_passed:
        failed_lines = []
        for c in all_checks:
            if c.get("outcome") in ("fail", "error"):
                check_value = c.get("check_value") or c.get("value")
                parts = [f"• [{c['data_source']}] {c['table']} → {c['name']}"]
                if check_value is not None:
                    parts.append(f"(actual: {check_value})")
                failed_lines.append(" ".join(parts))

        body = "\n".join(failed_lines) if failed_lines else "Check failed"
        _send_dq_alert("🚨", f"{total_failed} Failed", body, total_passed, total_failed, total_warn)
        raise Exception("Soda scan completed with failures or errors")

    else:
        _send_dq_alert(
            "✅", "All Passed",
            f"All {total_passed + total_failed + total_warn} checks passed.",
            total_passed, total_failed, total_warn,
        )
