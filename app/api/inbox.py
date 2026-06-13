"""Inbox, knowledge tree and second-opinion feed endpoints.

All read models expose product-facing names (proposal_type,
reviewer_id). Every write here is a human decision — the only kind of
write the platform allows outside ingestion.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.db.base import AsyncSessionLocal
from app.services.action_center import build_action_center
from app.services.agent_proposals import create_proposal
from app.services.agent_run_log import latest_runs
from app.services.command_center import build_command_center
from app.services.curated_updates import (
    UPDATE_KINDS,
    approve_update,
    build_update_draft,
)
from app.services.data_availability import get_availability
from app.services.data_quality_center import build_data_quality_center
from app.services.declarations import KNOWN_KEYS, get_declaration, set_declaration
from app.services.evidence_explorer import (
    build_source_event_view,
    investor_blocked,
    list_source_events,
)
from app.services.evidence_trail import build_finding_trail
from app.services.execution_view import build_execution_view, build_task_detail
from app.services.graph_tree import build_graph_tree, review_link
from app.services.inbox import (
    KIND_OWNERSHIP_ASSIGNMENT,
    build_inbox,
    decide_inbox_proposal,
)
from app.services.inbox_audit import (
    ACTION_ACTION_REVIEWED,
    ACTION_OWNER_ASSIGNMENT,
    record_inbox_action,
)
from app.services.notification_center import build_notification_center
from app.services.operating_rhythm import (
    build_daily_check,
    build_decision_review,
    build_weekly_review,
)
from app.services.product_view import build_product_view
from app.services.role_views import build_investor_view, build_team_workspace
from app.services.sales_view import build_sales_signals
from app.services.second_opinion import (
    FINDING_STATUSES,
    FINDING_TYPES,
    list_findings,
    set_finding_note,
    set_finding_status,
    snooze_finding,
)
from app.services.source_control import (
    SOURCE_ACTIONS,
    build_source_health,
    known_source_types,
    request_source_action,
)
from app.services.team_view import build_team_view
from app.api.view_guard import require_founder, require_scope, validated_view
from app.services.visibility import (
    SCOPE_FOUNDER,
    SCOPE_INVESTOR,
    SCOPE_TEAM,
    redact_finding,
)

router = APIRouter(tags=["inbox"])

# Shared audience gating (single source of truth in app.api.view_guard).
_validated_view = validated_view
_require_founder = require_founder
_require_scope = require_scope


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


class UpdateApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(min_length=8, max_length=128)
    reviewer_id: str = Field(default="founder", max_length=120)


class ActionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_ref: dict[str, Any]
    note: str | None = Field(default=None, max_length=500)
    reviewer_id: str = Field(default="founder", max_length=120)


class OwnerAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_key: str = Field(min_length=1, max_length=120)
    suggested_owner: str | None = Field(default=None, max_length=160)
    reason: str | None = Field(default=None, max_length=500)
    reviewer_id: str = Field(default="founder", max_length=120)


class SourceActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_key: str | None = Field(default=None, min_length=1, max_length=255)
    requested_by: str = Field(default="founder", max_length=120)
    input: dict[str, Any] = Field(default_factory=dict)


def _action_target_id(action_ref: dict[str, Any]) -> str:
    """Stable audit target id derived from an action's reference."""

    kind = str(action_ref.get("kind") or "action")
    for field in ("finding_key", "proposal_id", "issue_key", "metric_key"):
        value = action_ref.get(field)
        if value:
            return f"{kind}:{value}"
    return kind


@router.get("/v1/inbox")
async def get_inbox(view: str = Query(default=SCOPE_FOUNDER)) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_inbox(session)


@router.post("/v1/inbox/proposals/{proposal_id}/decision")
async def post_proposal_decision(
    proposal_id: str,
    request: ProposalDecisionRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    # Decisions are founder-only regardless of the declared view.
    _require_founder(view)
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
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
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
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
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
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
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
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
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


@router.get("/v1/founder/sources")
async def get_founder_sources(
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_source_health(session)


@router.post("/v1/founder/sources/{source_type}/{action_type}")
async def post_founder_source_action(
    source_type: str,
    action_type: str,
    request: SourceActionRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    if source_type not in known_source_types():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown source"
        )
    if action_type not in SOURCE_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown source action"
        )
    async with AsyncSessionLocal() as session:
        result = await request_source_action(
            session,
            source_type=source_type,
            action_type=action_type,
            request_key=request.request_key,
            requested_by=request.requested_by,
            input_payload=request.input,
        )
        await session.commit()
    return result


@router.get("/v1/founder/data-quality")
async def get_founder_data_quality(
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_data_quality_center(session)


@router.get("/v1/source-events")
async def get_source_events(
    source_object_id: str | None = Query(default=None),
    source_system: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
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
            source_system=source_system or source_type,
            status=status_filter,
            limit=limit,
            viewer_scope=viewer,
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


@router.get("/v1/founder/notification-center")
async def get_notification_center(
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    # The founder's internal review surface — no external delivery.
    _require_founder(view)
    async with AsyncSessionLocal() as session:
        return await build_notification_center(session)


# --- Stage 7: role dashboards (backend-redacted per audience) -----------


@router.get("/v1/team/workspace")
async def get_team_workspace(
    view: str = Query(default=SCOPE_TEAM),
) -> dict[str, Any]:
    # The team's working view; founder may preview, investor is blocked.
    _require_scope(view, {SCOPE_FOUNDER, SCOPE_TEAM})
    async with AsyncSessionLocal() as session:
        return await build_team_workspace(session)


@router.get("/v1/investor/view")
async def get_investor_view(
    view: str = Query(default=SCOPE_INVESTOR),
) -> dict[str, Any]:
    # Curated investor summary; founder may preview, team is blocked.
    _require_scope(view, {SCOPE_FOUNDER, SCOPE_INVESTOR})
    async with AsyncSessionLocal() as session:
        return await build_investor_view(session)


@router.get("/v1/operating-rhythm/{cadence}")
async def get_operating_rhythm(
    cadence: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    if cadence == "decision":
        # Pending decisions + raw audit trail are founder-only.
        _require_founder(view)
        async with AsyncSessionLocal() as session:
            return await build_decision_review(session)
    if cadence not in {"weekly", "daily"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown cadence: {cadence}",
        )
    viewer = _require_scope(view, {SCOPE_FOUNDER, SCOPE_TEAM})
    async with AsyncSessionLocal() as session:
        if cadence == "weekly":
            return await build_weekly_review(session, viewer_scope=viewer)
        return await build_daily_check(session, viewer_scope=viewer)


# --- Stage 7: curated updates (approve before export) -------------------


@router.get("/v1/updates/{kind}")
async def get_update_draft(
    kind: str,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    # The founder composes updates; each kind is redacted to its audience.
    _require_founder(view)
    if kind not in UPDATE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown update kind: {kind}",
        )
    async with AsyncSessionLocal() as session:
        return await build_update_draft(session, kind=kind)


@router.post("/v1/updates/{kind}/approve")
async def post_update_approve(
    kind: str,
    request: UpdateApproveRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    _require_founder(view)
    if kind not in UPDATE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown update kind: {kind}",
        )
    async with AsyncSessionLocal() as session:
        try:
            result = await approve_update(
                session,
                kind=kind,
                content_hash=request.content_hash,
                reviewer_id=request.reviewer_id,
            )
            await session.commit()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
    return result


# --- Stage 7: Action Center CTAs (safe, audited) ------------------------


@router.post("/v1/founder/action-center/review")
async def post_action_review(
    request: ActionReviewRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    # Acknowledge an action as reviewed — audit only, never a data mutation.
    _require_founder(view)
    target_id = _action_target_id(request.action_ref)
    async with AsyncSessionLocal() as session:
        await record_inbox_action(
            session,
            action=ACTION_ACTION_REVIEWED,
            actor=request.reviewer_id,
            target_id=target_id,
            previous_state={"reviewed": False},
            next_state={"reviewed": True},
            reversible=True,
            details={"action_ref": request.action_ref, "note": request.note},
        )
        await session.commit()
    return {"reviewed": True, "target_id": target_id}


@router.post("/v1/founder/action-center/assign-owner-proposal")
async def post_assign_owner_proposal(
    request: OwnerAssignmentRequest,
    view: str = Query(default=SCOPE_FOUNDER),
) -> dict[str, Any]:
    # Turn an owner suggestion into a tracked proposal. Idempotent on the
    # issue key; accepting it later only records a decision (no Jira write).
    _require_founder(view)
    proposal_id = f"ownership:{request.issue_key}"
    async with AsyncSessionLocal() as session:
        created = await create_proposal(
            session,
            proposal_id=proposal_id,
            agent="action_center",
            kind=KIND_OWNERSHIP_ASSIGNMENT,
            title=f"Назначить владельца: {request.issue_key}",
            payload={
                "issue_key": request.issue_key,
                "suggested_owner": request.suggested_owner,
                "reason": request.reason,
            },
            confidence=0.5,
            confidence_factors={"source": "action_center_cta"},
            dedupe_key=proposal_id,
        )
        if created:
            await record_inbox_action(
                session,
                action=ACTION_OWNER_ASSIGNMENT,
                actor=request.reviewer_id,
                target_id=proposal_id,
                previous_state=None,
                next_state={"status": "pending", "issue_key": request.issue_key},
                reversible=True,
                details={"suggested_owner": request.suggested_owner},
            )
        await session.commit()
    return {
        "proposal_id": proposal_id,
        "created": created,
        "idempotent": not created,
    }
