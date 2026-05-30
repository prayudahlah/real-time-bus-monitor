#!/bin/sh
set -e

CONNECTOR_PAYLOAD=$(cat <<EOF
{
  "name": "batch-pg-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "database.hostname": "postgres-batch",
    "database.port": "5432",
    "database.user": "postgres",
    "database.password": "${POSTGRES_PASSWORD}",
    "database.dbname": "batch_data",
    "topic.prefix": "cdc",
    "table.include.list": "public.routes,public.stops,public.trips,public.stop_times",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_slot",
    "publication.name": "debezium_pub",
    "publication.autocreate.mode": "filtered",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false",
    "transforms": "unwrap",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
    "transforms.unwrap.drop.tombstones": "false",
    "decimal.handling.mode": "double"
  }
}
EOF
)

for i in $(seq 1 30); do
  response=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$CONNECTOR_PAYLOAD" \
    "http://debezium-connect:8083/connectors" 2>/dev/null || echo "000")

  if [ "$response" = "201" ]; then
    echo "Connector registered successfully!"
    exit 0
  fi

  if [ "$response" = "409" ]; then
    echo "Connector already exists (HTTP 409) — skipping."
    exit 0
  fi

  echo "Waiting for Kafka Connect... ($i/30) - HTTP $response"
  sleep 3
done

echo "Failed to register connector after 30 attempts"
exit 1
