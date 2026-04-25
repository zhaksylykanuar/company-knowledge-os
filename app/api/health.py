from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "write_actions_enabled": settings.enable_write_actions,
        "llm_enabled": settings.enable_llm,
    }
