import os
import io
import logging

import psycopg2
from minio import Minio

logger = logging.getLogger(__name__)


class CopyProgressReader(io.StringIO):
    def __init__(self, initial_value, total, name):
        super().__init__(initial_value)
        self.total = total
        self.name = name
        self.read_so_far = 0
        self.last_quarter = -1

    def read(self, size=-1):
        data = super().read(size)
        if data:
            self.read_so_far += len(data)
            pct = self.read_so_far * 100 // self.total if self.total else 0
            quarter = pct // 25
            if quarter != self.last_quarter:
                logger.info(
                    "Copying %s... %s / %s bytes (%s%%)",
                    self.name,
                    f"{self.read_so_far:,}",
                    f"{self.total:,}",
                    pct,
                )
                self.last_quarter = quarter
        return data


def get_minio_client():
    endpoint = os.environ["MINIO_ENDPOINT"].replace("http://", "")
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def get_pg_conn():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def get_postgis_conn():
    return psycopg2.connect(
        host=os.environ["POSTGIS_HOST"],
        dbname=os.environ["POSTGIS_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
