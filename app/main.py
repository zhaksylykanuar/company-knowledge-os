from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.actions import router as actions_router
from app.api.auth import enforce_fail_closed_auth, get_current_actor, require_api_key
from app.api.auth_routes import router as auth_router
from app.api.briefings import router as briefings_router
from app.api.company_brain import router as company_brain_router
from app.api.company_map import router as company_map_router
from app.api.connectors import router as connectors_router
from app.api.dev import router as dev_router
from app.api.documents import router as documents_router
from app.api.drive import router as drive_router
from app.api.github import router as github_router
from app.api.gmail import router as gmail_router
from app.api.health import router as health_router
from app.api.headquarters import router as headquarters_router
from app.api.jira import router as jira_router
from app.api.workspace_company_brain import router as workspace_company_brain_router
from app.api.workspaces import router as workspaces_router
from app.core.config import resolved_cors_allowed_origins, settings
from app.core.logging import RequestLoggingMiddleware, configure_logging

# Configure basic application logging as early as possible (MVP §1.5 "basic
# logging"): a single sanitized handler at the configured level.
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail loudly at startup if a non-local deployment is not fail-closed.
    enforce_fail_closed_auth(settings)
    # Re-apply logging config on startup so the level reflects the current
    # environment even if settings changed after import (e.g. in tests).
    configure_logging(settings.log_level)
    yield


app = FastAPI(
    title="Company Knowledge & Decision OS",
    version="0.1.0",
    lifespan=lifespan,
)

# Basic request logging: method, path, status, duration — no bodies/secrets.
app.add_middleware(RequestLoggingMiddleware)

cors_allowed_origins = resolved_cors_allowed_origins(settings)
if cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            settings.api_auth_header_name,
        ],
        max_age=600,
    )

# Product routes accept EITHER a browser session cookie OR the operator API key
# (get_current_actor resolves both); the operator/CI path is unchanged.
protected_api_dependencies = [Depends(get_current_actor)]

app.include_router(health_router, prefix="/health", tags=["health"])
# Auth (login/logout/me/change-password) manages its own session auth — public.
app.include_router(auth_router)
app.include_router(workspaces_router, dependencies=protected_api_dependencies)
app.include_router(connectors_router, dependencies=protected_api_dependencies)
app.include_router(github_router, dependencies=protected_api_dependencies)
app.include_router(jira_router, dependencies=protected_api_dependencies)
app.include_router(gmail_router, dependencies=protected_api_dependencies)
app.include_router(drive_router, dependencies=protected_api_dependencies)
app.include_router(documents_router, dependencies=protected_api_dependencies)
app.include_router(headquarters_router, dependencies=protected_api_dependencies)
app.include_router(company_map_router, dependencies=protected_api_dependencies)
app.include_router(workspace_company_brain_router, dependencies=protected_api_dependencies)
app.include_router(briefings_router, dependencies=protected_api_dependencies)
app.include_router(actions_router, dependencies=protected_api_dependencies)
# Legacy filesystem Company Brain preview: operator-only. These routes are not
# workspace-scoped and therefore must never accept a browser session as product
# authorization. Workspace product reads use workspace_company_brain_router.
app.include_router(company_brain_router, dependencies=[Depends(require_api_key)])
# Local-dev-only browser bootstrap; intentionally public (hands the browser
# its local dev key) and gated to APP_ENV=local inside the route.
app.include_router(dev_router)
