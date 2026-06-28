from fastapi import APIRouter, Depends

from app.api.auth import require_api_key
from app.core.config import settings

router = APIRouter()


@router.get("")
async def health() -> dict[str, str]:
    """Public liveness probe.

    Intentionally minimal — no env or feature-flag detail is exposed to
    unauthenticated callers. Operator detail lives at /health/detail.
    """

    return {"status": "ok"}


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
