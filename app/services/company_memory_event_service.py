"""Strict append-only writes for the FounderOS lifecycle memory ledger."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import (
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_REJECTED,
    ActionProposal,
)
from app.db.company_world_models import CompanyWorldResolution
from app.db.canonical_models import SourceRecord
from app.db.memory_models import (
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED,
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_CREATED,
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_REJECTED,
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED,
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_DISMISSED,
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
    COMPANY_MEMORY_EVENT_VERSION,
    COMPANY_MEMORY_LIFECYCLE_CREATED,
    COMPANY_MEMORY_LIFECYCLE_RESOLVED,
    CompanyMemoryEvent,
    CompanyMemoryEventStream,
)


COMPANY_MEMORY_EVENT_EVIDENCE_LIMIT = 4
COMPANY_MEMORY_EVENT_SOURCE_KEYS = frozenset(
    {"github", "jira", "gmail", "drive", "internal"}
)
COMPANY_MEMORY_EVENT_REFERENCE_TYPES = frozenset(
    {
        "action_execution_event",
        "action_proposal",
        "company_world_resolution",
        "source_record",
        "sync_job",
    }
)

_EVENT_RULES = {
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_CREATED: (
        COMPANY_MEMORY_LIFECYCLE_CREATED,
        frozenset({"action_proposal"}),
    ),
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED: (
        COMPANY_MEMORY_LIFECYCLE_RESOLVED,
        frozenset({"action_proposal"}),
    ),
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_REJECTED: (
        COMPANY_MEMORY_LIFECYCLE_RESOLVED,
        frozenset({"action_proposal"}),
    ),
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED: (
        COMPANY_MEMORY_LIFECYCLE_RESOLVED,
        frozenset({"external_person_candidate", "organization_candidate"}),
    ),
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_DISMISSED: (
        COMPANY_MEMORY_LIFECYCLE_RESOLVED,
        frozenset({"external_person_candidate", "organization_candidate"}),
    ),
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED: (
        COMPANY_MEMORY_LIFECYCLE_RESOLVED,
        frozenset({"source_record"}),
    ),
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED: (
        COMPANY_MEMORY_LIFECYCLE_CREATED,
        frozenset({"source_record"}),
    ),
}


class CompanyMemoryEventConflictError(RuntimeError):
    """An idempotency key already identifies different event material."""


async def append_action_proposal_created_memory_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
) -> CompanyMemoryEvent:
    """Record the canonical creation fact without copying proposal content."""

    return await append_company_memory_event(
        session,
        workspace_id=proposal.workspace_id,
        event_type=COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_CREATED,
        subject_type="action_proposal",
        subject_key=str(proposal.id),
        subject_id=proposal.id,
        source_key=proposal.target_provider,
        actor_user_id=proposal.created_by_user_id,
        primary_source_record_id=None,
        evidence_refs=[_evidence_ref("action_proposal", proposal.id)],
        occurred_at=proposal.created_at,
        idempotency_material={
            "event_type": COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_CREATED,
            "proposal_id": proposal.id,
            "workspace_id": proposal.workspace_id,
        },
    )


async def append_action_proposal_decision_memory_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    actor_user_id: UUID,
    action_execution_event_id: UUID | None = None,
) -> CompanyMemoryEvent:
    """Record one terminal local proposal decision."""

    if proposal.status == ACTION_PROPOSAL_STATUS_APPROVED:
        event_type = COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED
        occurred_at = proposal.approved_at
    elif proposal.status == ACTION_PROPOSAL_STATUS_REJECTED:
        event_type = COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_REJECTED
        occurred_at = proposal.rejected_at
    else:
        raise ValueError("action proposal does not have a terminal review decision")
    evidence_refs = [_evidence_ref("action_proposal", proposal.id)]
    if action_execution_event_id is not None:
        evidence_refs.append(
            _evidence_ref("action_execution_event", action_execution_event_id)
        )
    return await append_company_memory_event(
        session,
        workspace_id=proposal.workspace_id,
        event_type=event_type,
        subject_type="action_proposal",
        subject_key=str(proposal.id),
        subject_id=proposal.id,
        source_key=proposal.target_provider,
        actor_user_id=actor_user_id,
        primary_source_record_id=None,
        evidence_refs=evidence_refs,
        occurred_at=occurred_at,
        idempotency_material={
            "event_type": event_type,
            "proposal_id": proposal.id,
            "workspace_id": proposal.workspace_id,
        },
    )


async def append_company_world_resolution_memory_event(
    session: AsyncSession,
    *,
    resolution: CompanyWorldResolution,
    occurred_at: datetime | None = None,
) -> CompanyMemoryEvent:
    """Record one terminal Company World resolution without candidate text."""

    if resolution.decision == "confirmed":
        event_type = COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED
    elif resolution.decision == "dismissed":
        event_type = COMPANY_MEMORY_EVENT_COMPANY_WORLD_DISMISSED
    else:
        raise ValueError("unsupported company world resolution decision")
    subject_type = f"{resolution.candidate_type}_candidate"
    return await append_company_memory_event(
        session,
        workspace_id=resolution.workspace_id,
        event_type=event_type,
        subject_type=subject_type,
        subject_key=resolution.candidate_version,
        subject_id=resolution.id,
        source_key="gmail",
        actor_user_id=resolution.actor_user_id,
        primary_source_record_id=resolution.source_record_id,
        evidence_refs=[
            _evidence_ref("company_world_resolution", resolution.id),
            _evidence_ref("source_record", resolution.source_record_id),
        ],
        occurred_at=occurred_at or resolution.created_at,
        idempotency_material={
            "event_type": event_type,
            "resolution_id": resolution.id,
            "workspace_id": resolution.workspace_id,
        },
    )


async def append_source_record_lifecycle_memory_event(
    session: AsyncSession,
    *,
    source_record: SourceRecord,
    sync_job_id: UUID,
    event_type: str,
    occurred_at: datetime,
) -> CompanyMemoryEvent:
    """Record one provider-attested disappearance or restoration."""

    if event_type not in {
        COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
        COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
    }:
        raise ValueError("unsupported source record lifecycle event")
    return await append_company_memory_event(
        session,
        workspace_id=source_record.workspace_id,
        event_type=event_type,
        subject_type="source_record",
        subject_key=str(source_record.id),
        subject_id=source_record.id,
        source_key=source_record.provider,
        actor_user_id=None,
        primary_source_record_id=source_record.id,
        evidence_refs=[
            _evidence_ref("source_record", source_record.id),
            _evidence_ref("sync_job", sync_job_id),
        ],
        occurred_at=occurred_at,
        idempotency_material={
            "event_type": event_type,
            "source_record_id": source_record.id,
            "sync_job_id": sync_job_id,
            "workspace_id": source_record.workspace_id,
        },
    )


async def append_company_memory_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    event_type: str,
    subject_type: str,
    subject_key: str,
    subject_id: UUID,
    source_key: str,
    actor_user_id: UUID | None,
    primary_source_record_id: UUID | None,
    evidence_refs: list[dict[str, str]],
    occurred_at: datetime | None,
    idempotency_material: dict[str, Any],
) -> CompanyMemoryEvent:
    """Append one validated event or return its exact idempotent replay."""

    lifecycle_state, allowed_subject_types = _EVENT_RULES.get(
        event_type,
        (None, frozenset()),
    )
    if lifecycle_state is None:
        raise ValueError("unsupported company memory event type")
    if subject_type not in allowed_subject_types:
        raise ValueError("company memory subject type does not match event type")
    if source_key not in COMPANY_MEMORY_EVENT_SOURCE_KEYS:
        raise ValueError("unsupported company memory source key")
    normalized_subject_key = _subject_key(subject_type, subject_key, subject_id)
    normalized_evidence = _validated_evidence_refs(evidence_refs)
    normalized_occurred_at = _utc_datetime(occurred_at)
    observed_at = datetime.now(timezone.utc)
    idempotency_key = f"cme1_{_digest(idempotency_material)}"
    fingerprint_material = {
        "access_scope": "workspace",
        "actor_user_id": actor_user_id,
        "confidence": 1.0,
        "event_type": event_type,
        "event_version": COMPANY_MEMORY_EVENT_VERSION,
        "evidence_refs": normalized_evidence,
        "lifecycle_state": lifecycle_state,
        "occurred_at": normalized_occurred_at,
        "primary_source_record_id": primary_source_record_id,
        "retention_policy": "workspace_canonical",
        "sensitivity": "internal",
        "source_key": source_key,
        "subject_id": subject_id,
        "subject_key": normalized_subject_key,
        "subject_type": subject_type,
        "workspace_id": workspace_id,
    }
    payload_fingerprint = _digest(fingerprint_material)

    existing = await session.scalar(
        select(CompanyMemoryEvent).where(
            CompanyMemoryEvent.workspace_id == workspace_id,
            CompanyMemoryEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        _assert_exact_replay(existing, payload_fingerprint)
        return existing

    event: CompanyMemoryEvent
    try:
        async with session.begin_nested():
            workspace_sequence = await _next_workspace_sequence(
                session,
                workspace_id=workspace_id,
            )
            event = CompanyMemoryEvent(
                workspace_id=workspace_id,
                workspace_sequence=workspace_sequence,
                event_version=COMPANY_MEMORY_EVENT_VERSION,
                event_type=event_type,
                lifecycle_state=lifecycle_state,
                subject_type=subject_type,
                subject_key=normalized_subject_key,
                subject_id=subject_id,
                source_key=source_key,
                confidence=1.0,
                access_scope="workspace",
                sensitivity="internal",
                retention_policy="workspace_canonical",
                actor_user_id=actor_user_id,
                primary_source_record_id=primary_source_record_id,
                evidence_refs=normalized_evidence,
                payload_fingerprint=payload_fingerprint,
                idempotency_key=idempotency_key,
                occurred_at=normalized_occurred_at,
                observed_at=observed_at,
            )
            session.add(event)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(CompanyMemoryEvent).where(
                CompanyMemoryEvent.workspace_id == workspace_id,
                CompanyMemoryEvent.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        _assert_exact_replay(existing, payload_fingerprint)
        return existing
    await session.refresh(event)
    return event


async def _next_workspace_sequence(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> int:
    statement = (
        insert(CompanyMemoryEventStream)
        .values(workspace_id=workspace_id, last_sequence=1)
        .on_conflict_do_update(
            index_elements=[CompanyMemoryEventStream.workspace_id],
            set_={
                "last_sequence": CompanyMemoryEventStream.last_sequence + 1,
            },
        )
        .returning(CompanyMemoryEventStream.last_sequence)
    )
    sequence = await session.scalar(statement)
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise RuntimeError("company memory workspace sequence is unavailable")
    return sequence


def _evidence_ref(reference_type: str, reference_id: UUID) -> dict[str, str]:
    return {
        "reference_type": reference_type,
        "reference_id": str(reference_id),
    }


def _validated_evidence_refs(
    evidence_refs: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not evidence_refs or len(evidence_refs) > COMPANY_MEMORY_EVENT_EVIDENCE_LIMIT:
        raise ValueError("company memory event requires bounded evidence refs")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in evidence_refs:
        if not isinstance(ref, dict) or set(ref) != {
            "reference_type",
            "reference_id",
        }:
            raise ValueError("company memory evidence ref must be a canonical identifier")
        reference_type = ref.get("reference_type")
        if reference_type not in COMPANY_MEMORY_EVENT_REFERENCE_TYPES:
            raise ValueError("unsupported company memory evidence reference type")
        try:
            reference_id = str(UUID(str(ref.get("reference_id"))))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "company memory evidence reference id must be a UUID"
            ) from exc
        key = (reference_type, reference_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "reference_type": reference_type,
                "reference_id": reference_id,
            }
        )
    if not normalized:
        raise ValueError("company memory event requires canonical evidence")
    return normalized


def _subject_key(subject_type: str, subject_key: str, subject_id: UUID) -> str:
    normalized = subject_key.strip().lower()
    if subject_type in {"action_proposal", "source_record"}:
        if normalized != str(subject_id):
            raise ValueError("company memory subject identity is inconsistent")
        return normalized
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("company world memory subject key must be a version hash")
    return normalized


def _utc_datetime(value: datetime | None) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("company memory event occurred_at is required")
    if value.tzinfo is None:
        raise ValueError("company memory event occurred_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _assert_exact_replay(
    event: CompanyMemoryEvent,
    payload_fingerprint: str,
) -> None:
    if event.payload_fingerprint != payload_fingerprint:
        raise CompanyMemoryEventConflictError(
            "company memory event idempotency conflict"
        )
