from fastapi import FastAPI

from app.api.events import router as events_router
from app.api.drive import router as drive_router
from app.api.extraction import router as extraction_router

app = FastAPI(title="Company Knowledge & Decision OS", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(events_router, prefix="/v1/events", tags=["events"])
app.include_router(drive_router)
app.include_router(extraction_router)