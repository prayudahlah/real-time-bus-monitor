import os
import time
import requests
import json
import logging
from kafka import KafkaProducer
from google.transit import gtfs_realtime_pb2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
WMATA_API_KEY = os.getenv("WMATA_API_KEY")
FETCH_INTERVAL_SEC = int(os.getenv("FETCH_INTERVAL_SEC", "30"))
VEHICLE_POSITIONS_URL = "https://api.wmata.com/gtfs/bus-gtfsrt-vehiclepositions.pb"

producer = None

def get_producer():
    global producer
    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
    return producer

def fetch_and_produce():
    if not WMATA_API_KEY:
        logger.error("WMATA_API_KEY tidak diset. Keluar.")
        return
    headers = {"api_key": WMATA_API_KEY}
    try:
        resp = requests.get(VEHICLE_POSITIONS_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        count = 0
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                v = entity.vehicle
                data = {
                    'bus_id': v.vehicle.id if v.vehicle.HasField('id') else 'unknown',
                    'lat': v.position.latitude,
                    'lon': v.position.longitude,
                    'speed': v.position.speed if v.position.HasField('speed') else 0.0,
                    'route_id': v.trip.route_id if v.trip.HasField('route_id') else '',
                    'trip_id': v.trip.trip_id if v.trip.HasField('trip_id') else '',
                    'start_date': v.trip.start_date if v.trip.HasField('start_date') else '',
                    'start_time': v.trip.start_time if v.trip.HasField('start_time') else '',
                    'timestamp': v.timestamp if v.HasField('timestamp') else int(time.time())
                }
                get_producer().send('bus.raw.vehicle_positions', data)
                count += 1
        logger.info(f"Produced {count} vehicle position records")
    except Exception as e:
        logger.error(f"Error fetching/producing: {e}")

def main():
    logger.info("WMATA Fetcher started. Fetch interval: {} sec".format(FETCH_INTERVAL_SEC))
    while True:
        try:
            get_producer()
            break
        except Exception as e:
            logger.warning(f"Waiting for Kafka... {e}")
            time.sleep(5)
    while True:
        fetch_and_produce()
        time.sleep(FETCH_INTERVAL_SEC)

if __name__ == "__main__":
    main()