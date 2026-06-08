import logging

from tasks.utils import get_pg_conn

logger = logging.getLogger(__name__)

DELETE_ORDER = [
    "stop_times",
    "trips",
    "stops",
    "routes",
    "calendar_dates",
    "calendar",
    "agency",
]


def main(**kwargs):
    conn = get_pg_conn()
    with conn.cursor() as cur:
        for table in DELETE_ORDER:
            logger.info("Deleting from %s...", table)
            cur.execute(f"DELETE FROM {table}")
            logger.info("Deleted %s rows from %s", f"{cur.rowcount:,}", table)
    conn.commit()
    conn.close()
    logger.info("All tables cleared")
