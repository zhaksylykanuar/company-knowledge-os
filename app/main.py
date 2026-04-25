from fastapi import FastAPI

from app.api.drive import router as drive_router
from app.api.events import router as events_router
from app.api.extraction import router as extraction_router
from app.api.gmail import router as gmail_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router

app = FastAPI(title="Company Knowledge & Decision OS", version="0.1.0")

app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(events_router, prefix="/v1/events", tags=["events"])
app.include_router(drive_router)
app.include_router(gmail_router)
app.include_router(extraction_router)
app.include_router(knowledge_router)
