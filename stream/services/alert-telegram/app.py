import os
import json
import logging
import time
import requests
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code != 200:
            logger.error(f"Telegram error: {r.text}")
        else:
            logger.info("Alert sent to Telegram")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")

def process_alert(alert_data):
    try:
        header = alert_data.get('header', 'No header')
        desc = alert_data.get('description', '')
        cause = alert_data.get('cause', 'Unknown')
        effect = alert_data.get('effect', 'Unknown')
        url = alert_data.get('url', '')
        routes = alert_data.get('routes', [])
        route_str = ", ".join(routes) if routes else "N/A"
        msg = (
            f"📢 <b>WMATA Service Alert</b>\n"
            f"<b>{header}</b>\n"
            f"Routes: {route_str}\n"
            f"{desc[:400]}{'...' if len(desc)>400 else ''}\n"
            f"Cause: {cause} | Effect: {effect}"
        )
        if url:
            msg += f"\n<a href=\"{url}\">More info</a>"
        send_telegram(msg)
    except Exception as e:
        logger.error(f"Alert processing error: {e}")

def create_consumer(topic):
    while True:
        try:
            return KafkaConsumer(
                topic,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
        except Exception as e:
            logger.warning(f"Waiting for Kafka (topic {topic})... {e}")
            time.sleep(5)

def main():
    alert_consumer = create_consumer('bus.service.alerts')
    logger.info("Alert Telegram: listening to bus.service.alerts")
    while True:
        for tp, msgs in alert_consumer.poll(timeout_ms=100).items():
            for msg in msgs:
                process_alert(msg.value)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
