from fastapi import FastAPI

app = FastAPI(title="ETA Inference Service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "inference"}


@app.get("/predict")
def predict():
    return {"message": "Not yet implemented"}
