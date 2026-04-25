from fastapi import FastAPI

from app.api.events import router as events_router
from app.api.drive import router as drive_router

app = FastAPI(title="Company Knowledge & Decision OS", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(events_router, prefix="/v1/events", tags=["events"])
app.include_router(drive_router)

from app.db.base import engine, Base


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)