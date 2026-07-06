from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import (
    ACTION_CREATED_BY_SYSTEM,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_INTERNAL_TODO,
    ActionProposal,
)
from app.db.briefing_models import Briefing, BriefingItem
from app.services.action_proposal_service import (
    ActionProposalCreateInput,
    create_action_proposal,
)
from app.services.briefing_persistence_service import get_briefing

BRIEFING_ACTION_PROPOSAL_GENERATION_WARNING = (
    "Briefing action proposal generation is local-only and does not execute provider actions."
)
BRIEFING_ACTION_PROPOSAL_NOT_FOUND = "briefing not found"
BRIEFING_ACTION_PROPOSAL_SOURCE = "briefing_non_github_signal"

ACTIONABLE_NON_GITHUB_BRIEFING_ITEM_KEYS = {
    "jira-work-items",
    "gmail-message-signals",
    "drive-file-signals",
}
OPEN_ACTION_STATUSES = {
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
}


class BriefingActionProposalGenerationError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BriefingActionProposalNotFoundError(BriefingActionProposalGenerationError):
    pass


@dataclass(frozen=True)
class BriefingActionProposalSkippedItem:
    item_key: str
    title: str
    reason: str


@dataclass(frozen=True)
class BriefingActionProposalGenerationResult:
    proposals: list[ActionProposal]
    skipped: list[BriefingActionProposalSkippedItem]


async def generate_action_proposals_from_briefing(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    briefing_id: UUID,
) -> BriefingActionProposalGenerationResult:
    """Create local internal-todo proposals from actionable persisted briefing items.

    This is a deterministic bridge from Founder Briefing to ActionProposal for
    the non-GitHub read-model items added in DEC-064. It reads only persisted
    briefing rows/evidence, writes only local ``ActionProposal`` rows, skips
    missing-evidence items, and never starts provider calls, external writes,
    sync, or LLM work.
    """

    briefing = await get_briefing(
        session,
        workspace_id=workspace_id,
        briefing_id=briefing_id,
    )
    if briefing is None:
        raise BriefingActionProposalNotFoundError(BRIEFING_ACTION_PROPOSAL_NOT_FOUND)

    existing_open_item_keys = await _existing_open_briefing_action_item_keys(
        session,
        workspace_id=workspace_id,
        briefing=briefing,
    )
    proposals: list[ActionProposal] = []
    skipped: list[BriefingActionProposalSkippedItem] = []

    for item in briefing.items:
        if item.item_key not in ACTIONABLE_NON_GITHUB_BRIEFING_ITEM_KEYS:
            continue
        if not item.evidence_refs:
            skipped.append(_skipped_item(item, reason="missing_evidence_refs"))
            continue
        if item.item_key in existing_open_item_keys:
            skipped.append(_skipped_item(item, reason="open_action_exists"))
            continue

        proposal = await create_action_proposal(
            session,
            workspace_id=workspace_id,
            created_by_user_id=None,
            payload=ActionProposalCreateInput(
                target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                action_type=ACTION_TYPE_INTERNAL_TODO,
                title=_proposal_title(item),
                description=_proposal_description(item),
                payload=_proposal_payload(briefing, item),
                evidence_refs=list(item.evidence_refs or [])[:20],
                briefing_item_id=item.id,
                created_by=ACTION_CREATED_BY_SYSTEM,
            ),
        )
        proposals.append(proposal)
        existing_open_item_keys.add(item.item_key)

    return BriefingActionProposalGenerationResult(
        proposals=proposals,
        skipped=skipped,
    )


async def _existing_open_briefing_action_item_keys(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    briefing: Briefing,
) -> set[str]:
    proposals = list(
        (
            await session.execute(
                select(ActionProposal)
                .where(ActionProposal.workspace_id == workspace_id)
                .where(ActionProposal.status.in_(OPEN_ACTION_STATUSES))
                .where(ActionProposal.target_provider == ACTION_TARGET_PROVIDER_INTERNAL)
                .where(ActionProposal.action_type == ACTION_TYPE_INTERNAL_TODO)
            )
        ).scalars()
    )
    item_ids_by_key = {item.item_key: item.id for item in briefing.items}
    open_item_keys: set[str] = set()
    for proposal in proposals:
        payload = proposal.payload if isinstance(proposal.payload, Mapping) else {}
        payload_briefing_id = _safe_text(payload.get("briefing_id"))
        payload_item_key = _safe_text(payload.get("briefing_item_key"))
        if payload_briefing_id == str(briefing.id) and payload_item_key:
            open_item_keys.add(payload_item_key)
            continue
        for item_key, item_id in item_ids_by_key.items():
            if proposal.briefing_item_id == item_id:
                open_item_keys.add(item_key)
                break
    return open_item_keys


def _skipped_item(
    item: BriefingItem,
    *,
    reason: str,
) -> BriefingActionProposalSkippedItem:
    return BriefingActionProposalSkippedItem(
        item_key=item.item_key,
        title=item.title,
        reason=reason,
    )


def _proposal_title(item: BriefingItem) -> str:
    return _clip_text(item.recommended_next_step or item.title, limit=500) or item.item_key


def _proposal_description(item: BriefingItem) -> str:
    parts = [item.title, item.summary]
    if item.recommended_next_step:
        parts.append(f"Recommended next step: {item.recommended_next_step}")
    return "\n\n".join(part for part in parts if part)


def _proposal_payload(briefing: Briefing, item: BriefingItem) -> dict[str, Any]:
    return {
        "source": BRIEFING_ACTION_PROPOSAL_SOURCE,
        "briefing_id": str(briefing.id),
        "briefing_item_key": item.item_key,
        "category": item.category,
        "severity": item.severity,
        "recommended_next_step": item.recommended_next_step,
        "related_entities": list(item.related_entities or [])[:20],
    }


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clip_text(value: Any, *, limit: int) -> str | None:
    text = _safe_text(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"
