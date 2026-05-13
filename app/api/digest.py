from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from app.services.digest import (
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    build_source_activity_digest,
)
from app.services.digest_rendering import render_source_activity_digest_text

router = APIRouter(prefix="/v1/digest", tags=["digest"])


async def _build_source_activity_digest_response(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int,
    debug_evidence: bool | None,
    debug_triage: bool | None,
) -> dict[str, Any]:
    try:
        return await build_source_activity_digest(
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            debug_evidence=debug_evidence,
            debug_triage=debug_triage,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/source-activity")
async def get_source_activity_digest(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
    debug_evidence: bool | None = Query(default=None),
    debug_triage: bool | None = Query(default=None),
) -> dict[str, Any]:
    return await _build_source_activity_digest_response(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
        debug_triage=debug_triage,
    )


@router.get("/source-activity/text", response_class=PlainTextResponse)
async def get_source_activity_digest_text(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
    debug_evidence: bool | None = Query(default=None),
    debug_triage: bool | None = Query(default=None),
) -> PlainTextResponse:
    digest = await _build_source_activity_digest_response(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
        debug_triage=debug_triage,
    )
    return PlainTextResponse(
        render_source_activity_digest_text(
            digest,
            debug_evidence=debug_evidence,
            debug_triage=debug_triage,
        )
    )
