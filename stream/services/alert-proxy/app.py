import os
import logging
import requests
from flask import Flask, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TOPIC_ID = int(os.environ.get("TELEGRAM_INFRA_TOPIC_ID", "0"))


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return "no data", 400

    alerts = data.get("alerts", [])
    if not alerts:
        return "no alerts", 200

    text_lines = []
    for alert in alerts:
        alertname = alert["labels"].get("alertname", "unknown")
        status = alert.get("status", "unknown")
        icon = "\u2705" if status == "resolved" else "\ud83d\udd25"
        summary = alert["annotations"].get("summary", "")
        if summary:
            text_lines.append(f"{icon} {alertname}: {summary}")
        else:
            text_lines.append(f"{icon} {alertname}")

    text = "\n".join(text_lines) if text_lines else "No alert details"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
    }
    if TOPIC_ID:
        payload["message_thread_id"] = TOPIC_ID

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=5,
        )
        logger.info(f"Telegram: {r.status_code}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
