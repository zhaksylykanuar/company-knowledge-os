from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.services.digest import (
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    build_source_activity_digest,
)

router = APIRouter(prefix="/v1/digest", tags=["digest"])


@router.get("/source-activity")
async def get_source_activity_digest(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(default=DEFAULT_DIGEST_ENTRY_LIMIT, ge=1, le=MAX_DIGEST_ENTRY_LIMIT),
) -> dict[str, Any]:
    try:
        return await build_source_activity_digest(
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
