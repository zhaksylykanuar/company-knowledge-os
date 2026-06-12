"""Inbox, knowledge tree and second-opinion feed endpoints.

All read models expose product-facing names (proposal_type,
reviewer_id). Every write here is a human decision — the only kind of
write the platform allows outside ingestion.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.db.base import AsyncSessionLocal
from app.services.data_availability import get_availability
from app.services.graph_tree import build_graph_tree, review_link
from app.services.inbox import build_inbox, decide_inbox_proposal
from app.services.second_opinion import (
    FINDING_STATUSES,
    FINDING_TYPES,
    list_findings,
    set_finding_note,
    set_finding_status,
    snooze_finding,
)

router = APIRouter(tags=["inbox"])


class ProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(accepted|rejected)$")
    reviewer_id: str = Field(default="founder", max_length=120)
    decision_reason: str | None = Field(default=None, max_length=500)


class FindingStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    note: str | None = Field(default=None, max_length=500)


class FindingSnoozeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=7, ge=1, le=90)


class FindingNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=500)


class LinkReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(confirm|remove)$")
    reviewer_id: str = Field(default="founder", max_length=120)


@router.get("/v1/inbox")
async def get_inbox() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        return await build_inbox(session)


@router.post("/v1/inbox/proposals/{proposal_id}/decision")
async def post_proposal_decision(
    proposal_id: str,
    request: ProposalDecisionRequest,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        try:
            result = await decide_inbox_proposal(
                session,
                proposal_id=proposal_id,
                decision=request.decision,
                reviewer_id=request.reviewer_id,
                decision_reason=request.decision_reason,
            )
            await session.commit()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found"
        )
    return result


@router.get("/v1/founder/second-opinion")
async def get_second_opinion_feed(
    status_filter: str | None = Query(default="open", alias="status"),
    finding_type: str | None = Query(default=None),
    include_snoozed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    if finding_type is not None and finding_type not in FINDING_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown finding_type: {finding_type}",
        )
    if status_filter is not None and status_filter not in FINDING_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown status: {status_filter}",
        )
    async with AsyncSessionLocal() as session:
        findings = await list_findings(
            session,
            status=status_filter,
            finding_type=finding_type,
            include_snoozed=include_snoozed,
            limit=limit,
        )
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_type[finding["finding_type"]] = by_type.get(finding["finding_type"], 0) + 1
        by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1
    return {
        "findings": findings,
        "counts": {
            "total": len(findings),
            "by_type": by_type,
            "by_severity": by_severity,
        },
    }


@router.post("/v1/founder/second-opinion/{finding_key:path}/status")
async def post_finding_status(
    finding_key: str,
    request: FindingStatusRequest,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        try:
            result = await set_finding_status(
                session,
                finding_key=finding_key,
                status=request.status,
                note=request.note,
            )
            await session.commit()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    return result


@router.post("/v1/founder/second-opinion/{finding_key:path}/snooze")
async def post_finding_snooze(
    finding_key: str,
    request: FindingSnoozeRequest,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await snooze_finding(
            session, finding_key=finding_key, days=request.days
        )
        await session.commit()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    return result


@router.post("/v1/founder/second-opinion/{finding_key:path}/note")
async def post_finding_note(
    finding_key: str,
    request: FindingNoteRequest,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await set_finding_note(
            session, finding_key=finding_key, note=request.note
        )
        await session.commit()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    return result


@router.get("/v1/graph/tree")
async def get_graph_tree() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        return await build_graph_tree(session)


@router.post("/v1/graph/links/{link_id:path}/review")
async def post_link_review(
    link_id: str,
    request: LinkReviewRequest,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        try:
            result = await review_link(
                session,
                link_id=link_id,
                decision=request.decision,
                reviewer_id=request.reviewer_id,
            )
            await session.commit()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="link not found"
        )
    return result


@router.get("/v1/founder/data-availability")
async def get_data_availability(
    scope: str | None = Query(default=None),
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        rows = await get_availability(session, scope=scope)
    return {"availability": rows}
