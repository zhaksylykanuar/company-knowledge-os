"""Inbox, knowledge tree and second-opinion feed endpoints.

All read models expose product-facing names (proposal_type,
reviewer_id). Every write here is a human decision — the only kind of
write the platform allows outside ingestion.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.db.base import AsyncSessionLocal
from app.services.agent_run_log import latest_runs
from app.services.command_center import build_command_center
from app.services.data_availability import get_availability
from app.services.declarations import KNOWN_KEYS, get_declaration, set_declaration
from app.services.evidence_explorer import (
    build_source_event_view,
    investor_blocked,
    list_source_events,
)
from app.services.evidence_trail import build_finding_trail
from app.services.graph_tree import build_graph_tree, review_link
from app.services.action_center import build_action_center
from app.services.execution_view import build_execution_view, build_task_detail
from app.services.inbox import build_inbox, decide_inbox_proposal
from app.services.product_view import build_product_view
from app.services.sales_view import build_sales_signals
from app.services.team_view import build_team_view
from app.services.second_opinion import (
    FINDING_STATUSES,
    FINDING_TYPES,
    list_findings,
    set_finding_note,
    set_finding_status,
    snooze_finding,
)
from app.services.visibility import (
    SCOPE_FOUNDER,
    SCOPE_INVESTOR,
    SCOPES,
    redact_finding,
)

router = APIRouter(tags=["inbox"])


def _validated_view(view: str) -> str:
    if view not in SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown view: {view}",
        )
    return view


def _require_founder(view: str) -> None:
    if _validated_view(view) != SCOPE_FOUNDER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="founder view required",
        )


class ProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(accepted|rejected)$")
    reviewer_id: str = Field(default="founder", max_length=120)
    decision_reason: str | None = Field(default=None, max_length=500)


class FindingStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    note: str | None = Field(default=None, max_length=500)
    reviewer_id: str = Field(default="founder", max_length=120)


class FindingSnoozeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=7, ge=1, le=90)
    reviewer_id: str = Field(default="founder", max_length=120)


class FindingNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=500)
    reviewer_id: str = Field(default="founder", max_length=120)


class DeclarationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict
    declared_by: str = Field(default="founder", max_length=120)


class LinkReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(confirm|remove)$")
    reviewer_id: str = Field(default="founder", max_length=120)


@router.get("/v1/inbox")
async def get_inbox(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    _require_founder(view)
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
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    viewer = _validated_view(view)
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
        raw_findings = await list_findings(
            session,
            status=status_filter,
            finding_type=finding_type,
            include_snoozed=include_snoozed,
            limit=limit,
        )
    findings = [
        redacted
        for item in raw_findings
        if (redacted := redact_finding(item, viewer)) is not None
    ]
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


@router.get("/v1/founder/second-opinion/{finding_key:path}/trail")
async def get_finding_trail(
    finding_key: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    # Raw evidence and source refs are founder-only by contract.
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        trail = await build_finding_trail(session, finding_key=finding_key)
    if trail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    return trail


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
                reviewer_id=request.reviewer_id,
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
            session,
            finding_key=finding_key,
            days=request.days,
            reviewer_id=request.reviewer_id,
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
            session,
            finding_key=finding_key,
            note=request.note,
            reviewer_id=request.reviewer_id,
        )
        await session.commit()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="finding not found"
        )
    return result


@router.get("/v1/graph/tree")
async def get_graph_tree(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    if _validated_view(view) == SCOPE_INVESTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="graph is not available in investor view",
        )
    async with AsyncSessionLocal() as session:
        return await build_graph_tree(session)


@router.get("/v1/founder/declarations/{key}")
async def get_founder_declaration(
    key: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    if key not in KNOWN_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown declaration key: {key}",
        )
    async with AsyncSessionLocal() as session:
        declaration = await get_declaration(session, key=key)
    return declaration or {"key": key, "payload": {}}


@router.put("/v1/founder/declarations/{key}")
async def put_founder_declaration(
    key: str,
    request: DeclarationRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        try:
            result = await set_declaration(
                session,
                key=key,
                payload=request.payload,
                declared_by=request.declared_by,
            )
            await session.commit()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
    return result


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


@router.get("/v1/source-events")
async def get_source_events(
    source_object_id: str | None = Query(default=None),
    source_system: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    viewer = _validated_view(view)
    if investor_blocked(viewer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="raw evidence is not available in investor view",
        )
    async with AsyncSessionLocal() as session:
        events = await list_source_events(
            session,
            source_object_id=source_object_id,
            source_system=source_system,
            limit=limit,
        )
    return {"events": events}


@router.get("/v1/source-events/{source_event_id}")
async def get_source_event_detail(
    source_event_id: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    viewer = _validated_view(view)
    if investor_blocked(viewer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="raw evidence is not available in investor view",
        )
    async with AsyncSessionLocal() as session:
        detail = await build_source_event_view(
            session, source_event_id=source_event_id, viewer_scope=viewer
        )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="source event not found"
        )
    return detail


@router.get("/v1/founder/command-center")
async def get_command_center(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_command_center(session)


@router.get("/v1/founder/sales-signals")
async def get_sales_signals(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    # Account/relationship signals are founder-scoped (communications).
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_sales_signals(session)


@router.get("/v1/founder/execution")
async def get_execution(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    if _validated_view(view) == SCOPE_INVESTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="execution view is not available to investors",
        )
    async with AsyncSessionLocal() as session:
        return await build_execution_view(session)


@router.get("/v1/founder/execution/tasks/{issue_key}")
async def get_task_detail(
    issue_key: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        detail = await build_task_detail(session, issue_key=issue_key)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
    return detail


@router.get("/v1/founder/team-load")
async def get_team_load(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    if _validated_view(view) == SCOPE_INVESTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="team load is not available to investors",
        )
    async with AsyncSessionLocal() as session:
        return await build_team_view(session)


@router.get("/v1/founder/product")
async def get_product(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    if _validated_view(view) == SCOPE_INVESTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="product detail is not available to investors",
        )
    async with AsyncSessionLocal() as session:
        return await build_product_view(session)


@router.get("/v1/founder/action-center")
async def get_action_center(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_action_center(session)


@router.get("/v1/founder/agent-runs")
async def get_agent_runs(
    limit: int = Query(default=20, ge=1, le=100),
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        runs = await latest_runs(session, limit=limit)
    return {"runs": runs}
