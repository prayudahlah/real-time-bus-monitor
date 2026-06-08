import logging

from airflow.exceptions import AirflowException
from tasks.utils import get_pg_conn, get_postgis_conn

logger = logging.getLogger(__name__)

NULL_THRESHOLD = 0.05

FK_CHECKS = [
    {
        "name": "stop_times.trip_id -> trips.trip_id",
        "sql": "SELECT COUNT(*) FROM stop_times st LEFT JOIN trips t ON st.trip_id = t.trip_id WHERE t.trip_id IS NULL",
    },
    {
        "name": "trips.route_id -> routes.route_id",
        "sql": "SELECT COUNT(*) FROM trips t LEFT JOIN routes r ON t.route_id = r.route_id WHERE r.route_id IS NULL",
    },
    {
        "name": "stop_times.stop_id -> stops.stop_id",
        "sql": "SELECT COUNT(*) FROM stop_times st LEFT JOIN stops s ON st.stop_id = s.stop_id WHERE s.stop_id IS NULL",
    },
]

NULL_CHECKS = [
    {"table": "stop_times", "column": "arrival_time"},
    {"table": "stop_times", "column": "departure_time"},
    {"table": "stop_times", "column": "stop_sequence"},
    {"table": "trips", "column": "route_id"},
    {"table": "trips", "column": "service_id"},
    {"table": "calendar", "column": "monday"},
    {"table": "calendar_dates", "column": "date"},
    {"table": "calendar_dates", "column": "exception_type"},
    {"table": "agency", "column": "agency_name"},
]


def _query(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main(**kwargs):
    conn = get_pg_conn()
    errors = []

    with conn.cursor() as cur:
        logger.info("--- Referential Integrity Checks ---")
        for check in FK_CHECKS:
            count = _query(cur, check["sql"])
            if count > 0:
                logger.error("FAIL: %s — %s violations", check["name"], count)
                errors.append(f"{check['name']}: {count} violations")
            else:
                logger.info("PASS: %s — 0 violations", check["name"])

        logger.info(
            "--- NULL Rate Checks (threshold: %.0f%%) ---", NULL_THRESHOLD * 100
        )
        for check in NULL_CHECKS:
            sql = (
                f"SELECT COUNT(*) FILTER (WHERE {check['column']} IS NULL)::float "
                f"/ NULLIF(COUNT(*), 0) FROM {check['table']}"
            )
            rate = _query(cur, sql)
            pct = rate * 100
            if rate >= NULL_THRESHOLD:
                logger.error(
                    "FAIL: %s.%s — NULL rate = %.2f%% (>= %.0f%%)",
                    check["table"],
                    check["column"],
                    pct,
                    NULL_THRESHOLD * 100,
                )
                errors.append(f"{check['table']}.{check['column']}: {pct:.2f}% NULL")
            elif rate > 0:
                logger.warning(
                    "WARN: %s.%s — NULL rate = %.2f%% (below %.0f%% threshold)",
                    check["table"],
                    check["column"],
                    pct,
                    NULL_THRESHOLD * 100,
                )
            else:
                logger.info(
                    "PASS: %s.%s — NULL rate = 0.00%%", check["table"], check["column"]
                )

    conn.close()

    logger.info("--- PostGIS Checks ---")
    pgis_conn = get_postgis_conn()
    with pgis_conn.cursor() as cur:
        stops_count = _query(cur, "SELECT COUNT(*) FROM stops")
        if stops_count < 7000:
            logger.error(
                "FAIL: stops — only %s rows (expected >= 7000)", f"{stops_count:,}"
            )
            errors.append(f"stops: only {stops_count} rows (expected >= 7000)")
        else:
            logger.info("PASS: stops — %s rows", f"{stops_count:,}")

        rp_count = _query(cur, "SELECT COUNT(*) FROM route_paths")
        if rp_count < 300:
            logger.error(
                "FAIL: route_paths — only %s rows (expected >= 300)", f"{rp_count:,}"
            )
            errors.append(f"route_paths: only {rp_count} rows (expected >= 300)")
        else:
            logger.info("PASS: route_paths — %s rows", f"{rp_count:,}")

        null_stops = _query(cur, "SELECT COUNT(*) FROM stops WHERE geom IS NULL")
        if null_stops > 0:
            logger.error("FAIL: stops — %s NULL geometries", null_stops)
            errors.append(f"stops: {null_stops} NULL geometries")
        else:
            logger.info("PASS: stops — 0 NULL geometries")

        null_rp = _query(cur, "SELECT COUNT(*) FROM route_paths WHERE geom IS NULL")
        if null_rp > 0:
            logger.error("FAIL: route_paths — %s NULL geometries", null_rp)
            errors.append(f"route_paths: {null_rp} NULL geometries")
        else:
            logger.info("PASS: route_paths — 0 NULL geometries")

    pgis_conn.close()

    if errors:
        raise AirflowException(f"Data quality validation failed:\n" + "\n".join(errors))

    logger.info("All data quality checks passed")
