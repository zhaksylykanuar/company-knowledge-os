from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.db.base import AsyncSessionLocal
from app.services.digest import (
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    build_persisted_attention_digest_read_model,
    build_source_activity_digest,
)
from app.services.digest_delivery_drafts import (
    DeliveryDraftDecisionConflictError,
    DeliveryDraftNotFoundError,
    approve_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft_from_db,
    create_persisted_attention_digest_delivery_draft,
    get_digest_delivery_draft_approval_status,
    get_persisted_digest_delivery_draft,
    reject_digest_delivery_draft,
)
from app.services.digest_rendering import (
    SAFE_EVIDENCE_REF_KEYS,
    render_persisted_attention_digest_text,
    render_source_activity_digest_text,
)

router = APIRouter(prefix="/v1/digest", tags=["digest"])


class DeliveryDraftDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


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


async def _build_persisted_attention_digest_response(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int,
) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as session:
            return await build_persisted_attention_digest_read_model(
                session,
                start_at=start_at,
                end_at=end_at,
                limit_per_section=limit,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def _build_persisted_attention_digest_delivery_draft_response(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int,
    debug_evidence: bool | None,
) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as session:
            return await build_persisted_attention_digest_delivery_draft_from_db(
                session,
                start_at=start_at,
                end_at=end_at,
                limit=limit,
                debug_evidence=bool(debug_evidence),
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def _create_persisted_attention_digest_delivery_draft_response(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int,
    debug_evidence: bool | None,
) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as session:
            draft = await create_persisted_attention_digest_delivery_draft(
                session,
                start_at=start_at,
                end_at=end_at,
                limit=limit,
                debug_evidence=bool(debug_evidence),
                actor="api",
            )
            await session.commit()
            return draft
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def _get_persisted_digest_delivery_draft_response(
    *,
    delivery_draft_id: str,
) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as session:
            draft = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="delivery draft was not found",
        )
    return draft


async def _get_digest_delivery_draft_approval_status_response(
    *,
    delivery_draft_id: str,
) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as session:
            approval_status = await get_digest_delivery_draft_approval_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if approval_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="delivery draft was not found",
        )
    return approval_status


async def _record_digest_delivery_draft_decision_response(
    *,
    delivery_draft_id: str,
    decision: str,
    request: DeliveryDraftDecisionRequest | None,
) -> dict[str, Any]:
    reviewer = request.reviewer if request is not None and request.reviewer else "api"
    note = request.note if request is not None else None

    try:
        async with AsyncSessionLocal() as session:
            if decision == "approved":
                approval_status = await approve_digest_delivery_draft(
                    session,
                    delivery_draft_id=delivery_draft_id,
                    reviewer=reviewer,
                    note=note,
                )
            else:
                approval_status = await reject_digest_delivery_draft(
                    session,
                    delivery_draft_id=delivery_draft_id,
                    reviewer=reviewer,
                    note=note,
                )
            await session.commit()
            return approval_status
    except DeliveryDraftNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryDraftDecisionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _safe_evidence_refs_for_preview(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    refs: list[dict[str, Any]] = []
    for ref in value:
        if not isinstance(ref, Mapping):
            continue
        safe_ref = {
            key: ref[key]
            for key in SAFE_EVIDENCE_REF_KEYS
            if ref.get(key) is not None
        }
        if safe_ref:
            refs.append(safe_ref)
    return refs


def _persisted_attention_digest_preview_response(
    digest: dict[str, Any],
    *,
    debug_evidence: bool | None,
) -> dict[str, Any]:
    include_debug_evidence = bool(debug_evidence)
    response = dict(digest)
    groups = digest.get("groups")
    safe_groups: dict[str, list[dict[str, Any]]] = {}
    if isinstance(groups, Mapping):
        for group_key, items in groups.items():
            safe_items: list[dict[str, Any]] = []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, Mapping):
                        continue
                    safe_item = dict(item)
                    if include_debug_evidence:
                        safe_item["evidence_refs"] = _safe_evidence_refs_for_preview(
                            safe_item.get("evidence_refs")
                        )
                        safe_item["activity_evidence_refs"] = (
                            _safe_evidence_refs_for_preview(
                                safe_item.get("activity_evidence_refs")
                            )
                        )
                    else:
                        safe_item.pop("evidence_refs", None)
                        safe_item.pop("activity_evidence_refs", None)
                    safe_items.append(safe_item)
            safe_groups[str(group_key)] = safe_items
    response["groups"] = safe_groups

    hidden_summary = digest.get("hidden_low_priority_summary")
    if isinstance(hidden_summary, Mapping):
        response["hidden_low_priority_summary"] = {
            "total": hidden_summary.get("total", 0),
            "counts": dict(hidden_summary.get("counts", {}))
            if isinstance(hidden_summary.get("counts"), Mapping)
            else {},
        }

    metadata = dict(digest.get("metadata", {})) if isinstance(digest.get("metadata"), Mapping) else {}
    metadata["debug_evidence"] = include_debug_evidence
    response["metadata"] = metadata
    return response


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


@router.get("/persisted-attention")
async def get_persisted_attention_digest(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
    debug_evidence: bool | None = Query(default=None),
) -> dict[str, Any]:
    digest = await _build_persisted_attention_digest_response(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
    )
    return _persisted_attention_digest_preview_response(
        digest,
        debug_evidence=debug_evidence,
    )


@router.get("/persisted-attention/text", response_class=PlainTextResponse)
async def get_persisted_attention_digest_text(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
    debug_evidence: bool | None = Query(default=None),
) -> PlainTextResponse:
    digest = await _build_persisted_attention_digest_response(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
    )
    preview = _persisted_attention_digest_preview_response(
        digest,
        debug_evidence=debug_evidence,
    )
    return PlainTextResponse(
        render_persisted_attention_digest_text(
            preview,
            debug_evidence=debug_evidence,
        )
    )


@router.get("/persisted-attention/delivery-draft")
async def get_persisted_attention_digest_delivery_draft(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
    debug_evidence: bool | None = Query(default=None),
) -> dict[str, Any]:
    return await _build_persisted_attention_digest_delivery_draft_response(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
    )


@router.post("/persisted-attention/delivery-draft")
async def create_persisted_attention_digest_delivery_draft_endpoint(
    start_at: datetime,
    end_at: datetime,
    limit: int = Query(
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        ge=1,
        le=MAX_DIGEST_ENTRY_LIMIT,
    ),
    debug_evidence: bool | None = Query(default=None),
) -> dict[str, Any]:
    return await _create_persisted_attention_digest_delivery_draft_response(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
    )


@router.get("/delivery-drafts/{delivery_draft_id}")
async def get_persisted_digest_delivery_draft_endpoint(
    delivery_draft_id: str,
) -> dict[str, Any]:
    return await _get_persisted_digest_delivery_draft_response(
        delivery_draft_id=delivery_draft_id,
    )


@router.post("/delivery-drafts/{delivery_draft_id}/approve")
async def approve_persisted_digest_delivery_draft_endpoint(
    delivery_draft_id: str,
    request: DeliveryDraftDecisionRequest | None = None,
) -> dict[str, Any]:
    return await _record_digest_delivery_draft_decision_response(
        delivery_draft_id=delivery_draft_id,
        decision="approved",
        request=request,
    )


@router.post("/delivery-drafts/{delivery_draft_id}/reject")
async def reject_persisted_digest_delivery_draft_endpoint(
    delivery_draft_id: str,
    request: DeliveryDraftDecisionRequest | None = None,
) -> dict[str, Any]:
    return await _record_digest_delivery_draft_decision_response(
        delivery_draft_id=delivery_draft_id,
        decision="rejected",
        request=request,
    )


@router.get("/delivery-drafts/{delivery_draft_id}/approval-status")
async def get_persisted_digest_delivery_draft_approval_status_endpoint(
    delivery_draft_id: str,
) -> dict[str, Any]:
    return await _get_digest_delivery_draft_approval_status_response(
        delivery_draft_id=delivery_draft_id,
    )
