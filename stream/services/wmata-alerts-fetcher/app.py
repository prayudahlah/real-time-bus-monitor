import os
import time
import requests
import json
import logging
from kafka import KafkaProducer
from google.transit import gtfs_realtime_pb2

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
WMATA_API_KEY = os.getenv("WMATA_API_KEY")
BUS_ALERTS_URL = "https://api.wmata.com/gtfs/bus-gtfsrt-alerts.pb"

CAUSE_MAP = {
    1: "Unknown Cause", 2: "Other", 3: "Technical Problem",
    4: "Strike", 5: "Demonstration", 6: "Accident",
    7: "Holiday", 8: "Weather", 9: "Maintenance",
    10: "Construction", 11: "Police Activity", 12: "Medical Emergency",
}

EFFECT_MAP = {
    1: "No Service", 2: "Reduced Service", 3: "Significant Delays",
    4: "Detour", 5: "Additional Service", 6: "Modified Service",
    7: "Other", 8: "Stop Moved", 9: "No Effect", 10: "Accessibility Issue",
}

seen_alert_ids = set()

producer = None

def get_producer():
    global producer
    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    return producer

def fetch_and_produce():
    if not WMATA_API_KEY:
        logger.error("WMATA_API_KEY not set")
        return
    headers = {"api_key": WMATA_API_KEY}
    try:
        resp = requests.get(BUS_ALERTS_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        count = 0
        for entity in feed.entity:
            if entity.HasField('alert'):
                alert_id = entity.id
                if alert_id in seen_alert_ids:
                    continue
                alert = entity.alert
                header_text = ""
                if alert.header_text.translation:
                    header_text = alert.header_text.translation[0].text
                desc_text = ""
                if alert.description_text.translation:
                    desc_text = alert.description_text.translation[0].text
                url = ""
                if alert.url.translation:
                    url = alert.url.translation[0].text
                routes = []
                for ie in alert.informed_entity:
                    if ie.route_id:
                        routes.append(ie.route_id)
                    if ie.HasField('trip') and ie.trip.route_id:
                        routes.append(ie.trip.route_id)
                active_start = None
                active_end = None
                if alert.active_period:
                    period = alert.active_period[0]
                    if period.HasField('start'):
                        active_start = period.start
                    if period.HasField('end'):
                        active_end = period.end
                seen_alert_ids.add(alert_id)
                data = {
                    "id": entity.id,
                    "header": header_text,
                    "description": desc_text,
                    "cause": CAUSE_MAP.get(alert.cause, "Unknown"),
                    "effect": EFFECT_MAP.get(alert.effect, "Unknown"),
                    "url": url,
                    "routes": routes,
                    "active_start": active_start,
                    "active_end": active_end,
                }
                get_producer().send("bus.service.alerts", data)
                count += 1
                logger.info(f"Alert produced: {entity.id} - {header_text[:50]}")
        logger.info(f"Produced {count} bus alerts total")
    except Exception as e:
        logger.error(f"Error fetching/producing: {e}")

def main():
    logger.info("WMATA Bus Alerts Fetcher started")
    while True:
        try:
            get_producer()
            break
        except Exception as e:
            logger.warning(f"Waiting for Kafka... {e}")
            time.sleep(5)
    while True:
        fetch_and_produce()
        time.sleep(60)

if __name__ == "__main__":
    main()