from fastapi import Depends, FastAPI

from app.api.auth import require_api_key
from app.api.drive import router as drive_router
from app.api.events import router as events_router
from app.api.extraction import router as extraction_router
from app.api.gmail import router as gmail_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router

app = FastAPI(title="Company Knowledge & Decision OS", version="0.1.0")

protected_api_dependencies = [Depends(require_api_key)]

app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(
    events_router,
    prefix="/v1/events",
    tags=["events"],
    dependencies=protected_api_dependencies,
)
app.include_router(drive_router, dependencies=protected_api_dependencies)
app.include_router(gmail_router, dependencies=protected_api_dependencies)
app.include_router(extraction_router, dependencies=protected_api_dependencies)
app.include_router(knowledge_router, dependencies=protected_api_dependencies)
