from prometheus_client import Counter, Histogram, Gauge

PREDICTIONS_TOTAL = Counter("inference_predictions_total", "Total predictions", ["route_id"])
ERRORS_TOTAL = Counter("inference_errors_total", "Total errors", ["error_type"])
LATENCY = Histogram("inference_latency_seconds", "Prediction latency", buckets=[0.1, 0.5, 1, 2, 5])
KAFKA_MESSAGES = Counter("inference_kafka_messages_consumed", "Kafka messages consumed")
MODEL_LOADED = Gauge("inference_model_loaded", "Model loaded flag", ["model_type"])
STOPS_LOADED = Gauge("inference_stops_loaded", "Number of stops loaded from PostgreSQL")
LAST_PREDICTION = Gauge("inference_last_prediction_timestamp", "Unix timestamp of last prediction")
