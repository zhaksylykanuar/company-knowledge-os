from fastapi import FastAPI

app = FastAPI(title="Company Knowledge & Decision OS", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}