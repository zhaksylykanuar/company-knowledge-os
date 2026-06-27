from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.actions import router as actions_router
from app.api.auth import enforce_fail_closed_auth, require_api_key
from app.api.briefings import router as briefings_router
from app.api.company_brain import router as company_brain_router
from app.api.dev import router as dev_router
from app.api.github import router as github_router
from app.api.health import router as health_router
from app.api.workspace_company_brain import router as workspace_company_brain_router
from app.api.workspaces import router as workspaces_router
from app.core.config import resolved_cors_allowed_origins, settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail loudly at startup if a non-local deployment is not fail-closed.
    enforce_fail_closed_auth(settings)
    yield


app = FastAPI(
    title="Company Knowledge & Decision OS",
    version="0.1.0",
    lifespan=lifespan,
)

cors_allowed_origins = resolved_cors_allowed_origins(settings)
if cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            settings.api_auth_header_name,
        ],
        max_age=600,
    )

protected_api_dependencies = [Depends(require_api_key)]

app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(workspaces_router, dependencies=protected_api_dependencies)
app.include_router(github_router, dependencies=protected_api_dependencies)
app.include_router(workspace_company_brain_router, dependencies=protected_api_dependencies)
app.include_router(briefings_router, dependencies=protected_api_dependencies)
app.include_router(actions_router, dependencies=protected_api_dependencies)
# Company Brain preview: read-only views over the local preview.
app.include_router(company_brain_router, dependencies=protected_api_dependencies)
# Local-dev-only browser bootstrap; intentionally public (hands the browser
# its local dev key) and gated to APP_ENV=local inside the route.
app.include_router(dev_router)
