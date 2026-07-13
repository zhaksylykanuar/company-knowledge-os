"""Explicit, idempotent founder resolution for Company World candidates."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GMAIL, SourceRecord
from app.db.company_world_models import (
    AFFILIATION_RELATIONSHIP_CONTACT,
    ORGANIZATION_RELATIONSHIP_UNKNOWN,
    PERSON_ORIGIN_FOUNDER_CONFIRMATION,
    PROFILE_STATUS_ACTIVE,
    Affiliation,
    CompanyWorldResolution,
    Interaction,
    Organization,
    Person,
)
from app.services.company_map_read_service import (
    _candidate_source_record_ids,
    _direction,
    _mailboxes,
    _normalize_email,
    _parse_mailbox,
    _safe_text,
    _safe_url,
    _subject_or_fallback,
    build_workspace_company_map,
)
from app.services.identity_service import list_workspace_members


class CompanyWorldResolutionError(RuntimeError):
    """Base error for a rejected candidate resolution."""


class CompanyWorldCandidateNotFoundError(CompanyWorldResolutionError):
    """Candidate does not exist in the requested workspace projection."""


class CompanyWorldResolutionConflictError(CompanyWorldResolutionError):
    """Candidate version, idempotency key, or prior decision conflicts."""


class CompanyWorldEvidenceError(CompanyWorldResolutionError):
    """Candidate lacks usable workspace-owned evidence."""


@dataclass(frozen=True)
class ResolveCompanyWorldCandidateCommand:
    candidate_type: str
    candidate_key: str
    candidate_version: str
    decision: str
    idempotency_key: str
    display_name: str | None = None
    organization_name: str | None = None
    relationship_type: str | None = None
    organization_relationship_kind: str | None = None
    role_title: str | None = None


@dataclass(frozen=True)
class CompanyWorldResolutionReceipt:
    resolution: CompanyWorldResolution
    person_id: UUID | None
    organization_id: UUID | None
    affiliation_id: UUID | None
    interaction_count: int
    replayed: bool


async def resolve_company_world_candidate(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    actor_user_id: UUID,
    command: ResolveCompanyWorldCandidateCommand,
) -> CompanyWorldResolutionReceipt:
    """Confirm or dismiss one server-resolved Company World candidate.

    The client supplies only a candidate key/version and founder-authored labels.
    Canonical email, domain, source records, and evidence are always resolved
    again inside the requested workspace.
    """

    request_hash = _command_hash(command)
    await lock_company_world_workspace(session=session, workspace_id=workspace_id)
    await _lock_resolution(
        session=session,
        workspace_id=workspace_id,
        idempotency_key=command.idempotency_key,
        candidate_type=command.candidate_type,
        candidate_key=command.candidate_key,
    )

    by_idempotency = await session.scalar(
        select(CompanyWorldResolution).where(
            CompanyWorldResolution.workspace_id == workspace_id,
            CompanyWorldResolution.idempotency_key == command.idempotency_key,
        )
    )
    if by_idempotency is not None:
        if by_idempotency.request_hash != request_hash:
            raise CompanyWorldResolutionConflictError(
                "idempotency key was already used with a different request"
            )
        return await _receipt_for_resolution(
            session=session,
            resolution=by_idempotency,
            replayed=True,
        )

    existing = await session.scalar(
        select(CompanyWorldResolution).where(
            CompanyWorldResolution.workspace_id == workspace_id,
            CompanyWorldResolution.candidate_type == command.candidate_type,
            CompanyWorldResolution.candidate_key == command.candidate_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise CompanyWorldResolutionConflictError(
                "candidate already has a different terminal resolution"
            )
        return await _receipt_for_resolution(
            session=session,
            resolution=existing,
            replayed=True,
        )

    candidate = await _resolve_candidate(
        session=session,
        workspace_id=workspace_id,
        candidate_type=command.candidate_type,
        candidate_key=command.candidate_key,
    )
    locked_records = await _lock_candidate_evidence(
        session=session,
        workspace_id=workspace_id,
        candidate=candidate,
    )
    try:
        candidate = await _resolve_candidate(
            session=session,
            workspace_id=workspace_id,
            candidate_type=command.candidate_type,
            candidate_key=command.candidate_key,
        )
    except CompanyWorldCandidateNotFoundError as exc:
        raise CompanyWorldResolutionConflictError(
            "candidate changed; refresh Company World before resolving it"
        ) from exc
    snapshot_source_record_ids = set(_candidate_source_record_ids(candidate))
    if snapshot_source_record_ids != set(locked_records):
        raise CompanyWorldResolutionConflictError(
            "candidate changed; refresh Company World before resolving it"
        )
    if candidate.get("candidate_version") != command.candidate_version:
        raise CompanyWorldResolutionConflictError(
            "candidate changed; refresh Company World before resolving it"
        )

    source_record = _primary_source_record(
        candidate=candidate,
        locked_records=locked_records,
    )

    person: Person | None = None
    organization: Organization | None = None
    affiliation: Affiliation | None = None
    interaction_count = 0
    now = datetime.now(timezone.utc)

    if command.decision == "confirmed":
        if command.candidate_type == "external_person":
            organization = await _resolved_organization_for_person_candidate(
                session=session,
                workspace_id=workspace_id,
                candidate=candidate,
                has_affiliation_intent=(
                    command.relationship_type is not None or command.role_title is not None
                ),
            )
            person = await _get_or_create_external_person(
                session=session,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                candidate=candidate,
                display_name=command.display_name,
                now=now,
            )
            if organization is not None and command.relationship_type:
                affiliation = await _get_or_create_affiliation(
                    session=session,
                    workspace_id=workspace_id,
                    actor_user_id=actor_user_id,
                    person=person,
                    organization=organization,
                    source_record=source_record,
                    relationship_type=command.relationship_type,
                    role_title=command.role_title,
                    now=now,
                )
            interaction_count = await materialize_person_interactions(
                session=session,
                workspace_id=workspace_id,
                person=person,
                organization=organization,
                apply=True,
                source_record_ids=snapshot_source_record_ids,
            )
        elif command.candidate_type == "organization":
            organization = await _get_or_create_organization(
                session=session,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                candidate_key=str(candidate["key"]),
                display_name=command.organization_name or command.display_name,
                relationship_kind=(
                    command.organization_relationship_kind or ORGANIZATION_RELATIONSHIP_UNKNOWN
                ),
                now=now,
            )
        else:  # guarded by the API model; retained for service callers.
            raise CompanyWorldCandidateNotFoundError("unsupported candidate type")

    resolution = CompanyWorldResolution(
        id=uuid4(),
        workspace_id=workspace_id,
        candidate_type=command.candidate_type,
        candidate_key=command.candidate_key,
        candidate_version=command.candidate_version,
        decision=command.decision,
        idempotency_key=command.idempotency_key,
        request_hash=request_hash,
        actor_user_id=actor_user_id,
        source_record_id=source_record.id,
        result_person_id=person.id if person else None,
        result_organization_id=organization.id if organization else None,
        result_affiliation_id=affiliation.id if affiliation else None,
    )
    session.add(resolution)
    await session.flush()
    return CompanyWorldResolutionReceipt(
        resolution=resolution,
        person_id=person.id if person else None,
        organization_id=organization.id if organization else None,
        affiliation_id=affiliation.id if affiliation else None,
        interaction_count=interaction_count,
        replayed=False,
    )


async def materialize_person_interactions(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    person: Person,
    organization: Organization | None,
    apply: bool,
    source_record_ids: set[UUID] | None = None,
) -> int:
    """Count or create all sanitized local Gmail interactions for one person."""

    email = _normalize_email(person.normalized_email or "")
    if not email:
        return 0
    memberships = await list_workspace_members(session, workspace_id=workspace_id)
    internal_emails = {_normalize_email(membership.user.email) for membership in memberships}
    records_statement = (
        select(SourceRecord)
        .where(SourceRecord.workspace_id == workspace_id)
        .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL)
        .where(SourceRecord.record_type == "message")
        .where(SourceRecord.is_deleted.is_(False))
        .order_by(SourceRecord.observed_at.asc(), SourceRecord.id.asc())
    )
    if source_record_ids is not None:
        if not source_record_ids:
            return 0
        records_statement = records_statement.where(SourceRecord.id.in_(source_record_ids))
    records = list((await session.execute(records_statement)).scalars())
    existing_source_ids = set(
        (
            await session.execute(
                select(Interaction.source_record_id).where(
                    Interaction.workspace_id == workspace_id,
                    Interaction.person_id == person.id,
                )
            )
        ).scalars()
    )

    proposed: list[Interaction] = []
    for record in records:
        message = _normalized_message(record.payload)
        sender = _parse_mailbox(message.get("from_address"))
        recipients = _mailboxes(message.get("to_addresses"))
        participant_emails = {
            mailbox[1] for mailbox in [sender, *recipients] if mailbox is not None
        }
        if email not in participant_emails or record.id in existing_source_ids:
            continue
        proposed.append(
            Interaction(
                id=uuid4(),
                workspace_id=workspace_id,
                person_id=person.id,
                organization_id=organization.id if organization else None,
                source_record_id=record.id,
                channel="email",
                direction=_direction(
                    sender_email=sender[1] if sender else None,
                    recipient_emails=[address for _name, address in recipients],
                    internal_emails=internal_emails,
                ),
                subject=_subject_or_fallback(message.get("subject"))[:500],
                occurred_at=record.source_updated_at or record.observed_at,
                source_url=_safe_url(message.get("source_url") or record.source_url),
            )
        )
    if apply and proposed:
        session.add_all(proposed)
        await session.flush()
    return len(proposed)


async def _resolve_candidate(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    candidate_type: str,
    candidate_key: str,
) -> dict[str, Any]:
    projection = await build_workspace_company_map(
        session=session,
        workspace_id=workspace_id,
        include_durable=False,
    )
    if candidate_type == "external_person":
        candidates = projection["people"]["external_candidates"]
    elif candidate_type == "organization":
        candidates = projection["organizations"]
    else:
        raise CompanyWorldCandidateNotFoundError("candidate not found")
    candidate = next(
        (row for row in candidates if row.get("key") == candidate_key),
        None,
    )
    if candidate is None:
        raise CompanyWorldCandidateNotFoundError("candidate not found")
    return candidate


async def _lock_candidate_evidence(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    candidate: Mapping[str, Any],
) -> dict[UUID, SourceRecord]:
    record_ids = _candidate_source_record_ids(candidate)
    if not record_ids:
        raise CompanyWorldEvidenceError("candidate has no source record evidence")
    records = list(
        (
            await session.execute(
                select(SourceRecord)
                .where(
                    SourceRecord.workspace_id == workspace_id,
                    SourceRecord.id.in_(record_ids),
                    SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL,
                    SourceRecord.record_type == "message",
                    SourceRecord.is_deleted.is_(False),
                )
                .with_for_update(read=True)
            )
        ).scalars()
    )
    locked_records = {record.id: record for record in records}
    if set(locked_records) != set(record_ids):
        raise CompanyWorldEvidenceError("candidate evidence is unavailable")
    return locked_records


def _primary_source_record(
    *,
    candidate: Mapping[str, Any],
    locked_records: Mapping[UUID, SourceRecord],
) -> SourceRecord:
    for record_id in _candidate_source_record_ids(candidate):
        source_record = locked_records.get(record_id)
        if source_record is not None:
            return source_record
    raise CompanyWorldEvidenceError("candidate evidence is unavailable")


async def _resolved_organization_for_person_candidate(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    candidate: Mapping[str, Any],
    has_affiliation_intent: bool,
) -> Organization | None:
    organization_key = candidate.get("organization_key")
    if not isinstance(organization_key, str) or not organization_key:
        if has_affiliation_intent:
            raise CompanyWorldResolutionConflictError(
                "affiliation fields require a confirmed organization candidate"
            )
        return None

    resolution = await session.scalar(
        select(CompanyWorldResolution).where(
            CompanyWorldResolution.workspace_id == workspace_id,
            CompanyWorldResolution.candidate_type == "organization",
            CompanyWorldResolution.candidate_key == organization_key,
        )
    )
    if resolution is None:
        raise CompanyWorldResolutionConflictError(
            "organization candidate must be resolved before confirming this person"
        )
    if resolution.decision == "dismissed":
        if has_affiliation_intent:
            raise CompanyWorldResolutionConflictError(
                "affiliation fields require a confirmed organization candidate"
            )
        return None
    if resolution.result_organization_id is None:
        raise CompanyWorldEvidenceError(
            "confirmed organization resolution has no durable organization"
        )
    organization = await session.scalar(
        select(Organization).where(
            Organization.workspace_id == workspace_id,
            Organization.id == resolution.result_organization_id,
        )
    )
    if organization is None:
        raise CompanyWorldEvidenceError("confirmed organization is unavailable")
    return organization


async def _get_or_create_external_person(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    actor_user_id: UUID,
    candidate: Mapping[str, Any],
    display_name: str | None,
    now: datetime,
) -> Person:
    normalized_email = _normalize_email(str(candidate["email"]))
    existing = await session.scalar(
        select(Person).where(
            Person.workspace_id == workspace_id,
            Person.normalized_email == normalized_email,
        )
    )
    if existing is not None:
        return existing
    person = Person(
        id=uuid4(),
        workspace_id=workspace_id,
        user_id=None,
        normalized_email=normalized_email,
        display_name=(
            _safe_text(display_name)
            or _safe_text(candidate.get("display_name"))
            or normalized_email
        ),
        origin=PERSON_ORIGIN_FOUNDER_CONFIRMATION,
        status=PROFILE_STATUS_ACTIVE,
        confirmed_by_user_id=actor_user_id,
        confirmed_at=now,
    )
    session.add(person)
    await session.flush()
    return person


async def _get_or_create_organization(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    actor_user_id: UUID,
    candidate_key: str,
    display_name: str | None,
    relationship_kind: str,
    now: datetime,
) -> Organization:
    existing = await session.scalar(
        select(Organization).where(
            Organization.workspace_id == workspace_id,
            Organization.canonical_key == candidate_key,
        )
    )
    if existing is not None:
        return existing
    domain = candidate_key.removeprefix("organization:").strip().casefold()
    if not domain or domain == candidate_key:
        raise CompanyWorldCandidateNotFoundError("organization candidate not found")
    organization = Organization(
        id=uuid4(),
        workspace_id=workspace_id,
        canonical_key=candidate_key,
        normalized_domain=domain,
        display_name=_safe_text(display_name) or domain,
        relationship_kind=relationship_kind,
        status=PROFILE_STATUS_ACTIVE,
        confirmed_by_user_id=actor_user_id,
        confirmed_at=now,
    )
    session.add(organization)
    await session.flush()
    return organization


async def _get_or_create_affiliation(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    actor_user_id: UUID,
    person: Person,
    organization: Organization,
    source_record: SourceRecord,
    relationship_type: str,
    role_title: str | None,
    now: datetime,
) -> Affiliation:
    existing = await session.scalar(
        select(Affiliation).where(
            Affiliation.workspace_id == workspace_id,
            Affiliation.person_id == person.id,
            Affiliation.organization_id == organization.id,
        )
    )
    if existing is not None:
        return existing
    affiliation = Affiliation(
        id=uuid4(),
        workspace_id=workspace_id,
        person_id=person.id,
        organization_id=organization.id,
        relationship_type=relationship_type or AFFILIATION_RELATIONSHIP_CONTACT,
        role_title=_safe_text(role_title),
        source_record_id=source_record.id,
        confirmed_by_user_id=actor_user_id,
        confirmed_at=now,
        status=PROFILE_STATUS_ACTIVE,
    )
    session.add(affiliation)
    await session.flush()
    return affiliation


async def _receipt_for_resolution(
    *,
    session: AsyncSession,
    resolution: CompanyWorldResolution,
    replayed: bool,
) -> CompanyWorldResolutionReceipt:
    interaction_count = 0
    if resolution.result_person_id is not None:
        interaction_count = int(
            await session.scalar(
                select(func.count(Interaction.id)).where(
                    Interaction.workspace_id == resolution.workspace_id,
                    Interaction.person_id == resolution.result_person_id,
                )
            )
            or 0
        )
    return CompanyWorldResolutionReceipt(
        resolution=resolution,
        person_id=resolution.result_person_id,
        organization_id=resolution.result_organization_id,
        affiliation_id=resolution.result_affiliation_id,
        interaction_count=interaction_count,
        replayed=replayed,
    )


async def lock_company_world_workspace(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> None:
    """Serialize every Company World write inside one workspace transaction."""

    lock_key = f"company-world:workspace:{workspace_id}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )


async def _lock_resolution(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    idempotency_key: str,
    candidate_type: str,
    candidate_key: str,
) -> None:
    # PostgreSQL transaction advisory locks serialize both idempotency-key and
    # candidate decisions without reading or exposing any candidate content.
    keys = (
        f"company-world:idempotency:{workspace_id}:{idempotency_key}",
        f"company-world:candidate:{workspace_id}:{candidate_type}:{candidate_key}",
    )
    for lock_key in keys:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )


def _command_hash(command: ResolveCompanyWorldCandidateCommand) -> str:
    payload = {
        "candidate_type": command.candidate_type,
        "candidate_key": command.candidate_key,
        "candidate_version": command.candidate_version,
        "decision": command.decision,
        "display_name": command.display_name,
        "organization_name": command.organization_name,
        "relationship_type": command.relationship_type,
        "organization_relationship_kind": command.organization_relationship_kind,
        "role_title": command.role_title,
    }
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(material.encode("utf-8")).hexdigest()


def _normalized_message(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    message = payload.get("normalized_message")
    return message if isinstance(message, Mapping) else {}
