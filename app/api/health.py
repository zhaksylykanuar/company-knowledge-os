import asyncio
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import require_api_key
from app.core.config import settings
from app.core.logging import runtime_request_metrics
from app.db.base import AsyncSessionLocal

router = APIRouter()


@router.get("")
async def health() -> dict[str, str]:
    """Public liveness probe.

    Intentionally minimal — no env or feature-flag detail is exposed to
    unauthenticated callers. Operator detail lives at /health/detail.
    """

    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def readiness() -> dict[str, str] | JSONResponse:
    """Public, minimal database-backed readiness probe."""

    try:
        async with asyncio.timeout(settings.readiness_database_timeout_seconds):
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, TimeoutError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable"},
        )
    return {"status": "ready"}


@router.get("/detail", dependencies=[Depends(require_api_key)])
async def health_detail() -> dict[str, str | bool]:
    """Operator-only health detail: environment and feature-flag posture."""

    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "write_actions_enabled": settings.enable_write_actions,
        "llm_enabled": settings.enable_llm,
    }


@router.get("/metrics", dependencies=[Depends(require_api_key)])
async def health_metrics() -> dict[str, Any]:
    """Operator-only low-cardinality process counters."""

    return {
        "status": "ok",
        "scope": "process",
        "metrics": runtime_request_metrics.snapshot(),
    }
