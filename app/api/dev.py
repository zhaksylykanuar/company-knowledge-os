"""Local-dev-only endpoints. Public (no API key — this is what hands the
browser its dev key), but gated to APP_ENV=local + the explicit flag, so
they are simply absent (404) in any non-local deployment.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.services.browser_config import (
    browser_dev_config_enabled,
    sanitize_browser_config,
)

router = APIRouter(prefix="/v1/dev", tags=["dev"])


@router.get("/browser-config")
async def get_browser_config() -> dict[str, Any]:
    # Only exists in local dev with the flag on; otherwise it does not exist.
    if not browser_dev_config_enabled(settings):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not found"
        )
    return sanitize_browser_config(settings)
