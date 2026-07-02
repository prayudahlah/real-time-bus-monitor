FROM python:3.11-slim

RUN pip install --no-cache-dir mlflow==3.14.0 boto3 psycopg2-binary gunicorn

ENV MLFLOW_TRACKING_URI=http://0.0.0.0:5000

EXPOSE 5000

CMD mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --backend-store-uri ${BACKEND_STORE_URI} \
    --default-artifact-root ${ARTIFACT_ROOT} \
    --artifacts-destination ${ARTIFACT_ROOT}
