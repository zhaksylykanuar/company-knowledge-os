from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parseaddr
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GMAIL, SourceRecord
from app.db.company_world_models import (
    PERSON_ORIGIN_FOUNDER_CONFIRMATION,
    PROFILE_STATUS_ACTIVE,
    Affiliation,
    CompanyWorldResolution,
    Interaction,
    Organization,
    Person,
)
from app.db.identity_models import USER_STATUS_ACTIVE, Membership, User, Workspace
from app.services.company_brain_github_read_service import (
    _gmail_message_payload,
    build_workspace_company_brain,
)
from app.services.identity_service import WorkspaceMembership, list_workspace_members

COMPANY_MAP_MODE = "evidence_backed_projection"
COMPANY_MAP_SOURCE = "workspace_and_company_brain_projection"
RESOLUTION_ONLY_MESSAGE_LIMIT = 100

# Consumer mailbox domains do not identify a customer organization. They remain
# external people candidates until a founder confirms their real affiliation.
GENERIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "yandex.com",
        "yandex.ru",
        "mail.ru",
        "proton.me",
        "protonmail.com",
    }
)


async def build_workspace_company_map(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    limit: int = 100,
    include_durable: bool = True,
    resolution_only: bool = False,
    access_role: str | None = None,
) -> dict[str, Any]:
    """Build a read-only, evidence-backed map of people and organizations.

    The projection deliberately labels external people and email-domain
    organizations as candidates. It never infers that somebody is an employee,
    customer, decision maker, or account owner without founder confirmation.
    ``resolution_only`` reads only a bounded Gmail window, participant-matched
    active members, and durable keys needed to suppress resolved candidates.
    """

    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace not found")

    message_limit = min(max(limit, 0), RESOLUTION_ONLY_MESSAGE_LIMIT) if resolution_only else limit
    if resolution_only:
        messages = await _bounded_gmail_message_rows(
            session=session,
            workspace_id=workspace_id,
            limit=message_limit,
        )
    else:
        brain = await build_workspace_company_brain(
            session=session,
            workspace_id=workspace_id,
            limit=message_limit,
        )
        communications = brain.get("communications")
        raw_messages = (
            communications.get("messages", []) if isinstance(communications, Mapping) else []
        )
        messages = raw_messages if isinstance(raw_messages, list) else []
    memberships = (
        await _matching_active_workspace_members(
            session=session,
            workspace=workspace,
            participant_emails=_message_participant_emails(messages),
        )
        if resolution_only
        else await list_workspace_members(session, workspace_id=workspace_id)
    )
    gmail_messages_available = await _gmail_message_count(
        session=session,
        workspace_id=workspace_id,
    )

    internal_people = [
        {
            "key": f"user:{membership.user.id}",
            "user_id": membership.user.id,
            "name": membership.user.name,
            "email": membership.user.email,
            "status": membership.user.status,
            "role": membership.membership.role,
            "source_refs": [
                {
                    "id": f"membership:{membership.membership.id}",
                    "kind": "workspace_membership",
                    "source": "founderos",
                    "label": membership.membership.role,
                    "url": None,
                    "record_type": "membership",
                    "record_id": membership.membership.id,
                }
            ],
        }
        for membership in memberships
    ]
    internal_keys = {
        _normalize_email(membership.user.email): f"user:{membership.user.id}"
        for membership in memberships
    }

    external_people: dict[str, dict[str, Any]] = {}
    organizations: dict[str, dict[str, Any]] = {}
    touchpoints: list[dict[str, Any]] = []

    for raw_message in messages:
        sender = _parse_mailbox(raw_message.get("from_address"))
        recipients = _mailboxes(raw_message.get("to_addresses"))
        participants = [mailbox for mailbox in [sender, *recipients] if mailbox]
        participant_by_email = {mailbox[1]: mailbox for mailbox in participants}
        external_mailboxes = [
            mailbox for email, mailbox in participant_by_email.items() if email not in internal_keys
        ]

        source_refs = _source_refs(
            raw_message.get("source_refs"),
            canonical_source=SOURCE_RECORD_PROVIDER_GMAIL,
        )
        occurred_at = _datetime_or_none(raw_message.get("received_at"))
        person_keys = [
            internal_keys[email] if email in internal_keys else _external_person_key(email)
            for email in sorted(participant_by_email)
        ]
        organization_keys = sorted(
            {
                key
                for _display_name, email in external_mailboxes
                if (key := _organization_key_for_email(email)) is not None
            }
        )

        touchpoints.append(
            {
                "key": f"touchpoint:{raw_message.get('source_record_id')}",
                "channel": "email",
                "source_record_id": raw_message.get("source_record_id"),
                "subject": _subject_or_fallback(raw_message.get("subject")),
                "direction": _direction(
                    sender_email=sender[1] if sender else None,
                    recipient_emails=[email for _name, email in recipients],
                    internal_emails=set(internal_keys),
                ),
                "occurred_at": occurred_at,
                "person_keys": person_keys,
                "organization_keys": organization_keys,
                "source_url": _safe_url(raw_message.get("source_url")),
                "source_refs": source_refs,
            }
        )

        for display_name, email in external_mailboxes:
            person_key = _external_person_key(email)
            organization_key = _organization_key_for_email(email)
            person = external_people.setdefault(
                email,
                {
                    "key": person_key,
                    "email": email,
                    "display_name": display_name,
                    "organization_key": organization_key,
                    "last_interaction_at": occurred_at,
                    "interaction_count": 0,
                    "source_refs": [],
                    "needs_founder_confirm": True,
                },
            )
            if person["display_name"] is None and display_name:
                person["display_name"] = display_name
            person["interaction_count"] += 1
            person["last_interaction_at"] = _latest_datetime(
                person["last_interaction_at"], occurred_at
            )
            person["source_refs"] = _merge_source_refs(person["source_refs"], source_refs)

        for organization_key in organization_keys:
            domain = organization_key.removeprefix("organization:")
            organization = organizations.setdefault(
                organization_key,
                {
                    "key": organization_key,
                    "domain": domain,
                    "name": None,
                    "kind": "external_candidate",
                    "people": set(),
                    "interaction_count": 0,
                    "last_interaction_at": occurred_at,
                    "source_refs": [],
                    "needs_founder_confirm": True,
                },
            )
            organization["people"].update(
                email
                for _display_name, email in external_mailboxes
                if _organization_key_for_email(email) == organization_key
            )
            organization["interaction_count"] += 1
            organization["last_interaction_at"] = _latest_datetime(
                organization["last_interaction_at"], occurred_at
            )
            organization["source_refs"] = _merge_source_refs(
                organization["source_refs"], source_refs
            )

    external_rows = sorted(
        external_people.values(),
        key=lambda row: (
            row["last_interaction_at"] or datetime.min.replace(tzinfo=timezone.utc),
            row["email"],
        ),
        reverse=True,
    )
    organization_rows = [
        {
            **{key: value for key, value in organization.items() if key != "people"},
            "people_count": len(organization["people"]),
        }
        for organization in organizations.values()
    ]
    payload_hashes = await _candidate_payload_hashes(
        session=session,
        workspace_id=workspace_id,
        candidates=[*external_rows, *organization_rows],
    )
    for row in external_rows:
        row["candidate_version"] = _candidate_version(row, payload_hashes)
    for row in organization_rows:
        row["candidate_version"] = _candidate_version(row, payload_hashes)
    organization_rows.sort(
        key=lambda row: (
            row["last_interaction_at"] or datetime.min.replace(tzinfo=timezone.utc),
            row["domain"],
        ),
        reverse=True,
    )
    touchpoints.sort(
        key=lambda row: row["occurred_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    if resolution_only:
        durable = await _resolution_only_company_world_rows(
            session=session,
            workspace_id=workspace_id,
            external_candidate_keys={row["key"] for row in external_rows},
            organization_candidate_keys={row["key"] for row in organization_rows},
        )
    elif include_durable:
        durable = await _durable_company_world_rows(
            session=session,
            workspace_id=workspace_id,
        )
    else:
        durable = _empty_durable_rows()
    resolved_candidates = durable["resolved_candidates"]
    external_rows = [
        row
        for row in external_rows
        if ("external_person", row["key"]) not in resolved_candidates
        and row["key"] not in durable["confirmed_person_candidate_keys"]
    ]
    organization_rows = [
        row
        for row in organization_rows
        if ("organization", row["key"]) not in resolved_candidates
        and row["key"] not in durable["confirmed_organization_candidate_keys"]
    ]
    for person in internal_people:
        person["person_id"] = durable["person_ids_by_user_id"].get(person["user_id"])
    for touchpoint in touchpoints:
        touchpoint["person_keys"] = [
            durable["candidate_person_key_map"].get(key, key) for key in touchpoint["person_keys"]
        ]
        touchpoint["organization_keys"] = [
            durable["candidate_organization_key_map"].get(key, key)
            for key in touchpoint["organization_keys"]
        ]

    warnings: list[str] = []
    if not messages:
        warnings.append(
            "В канонических данных рабочего пространства пока нет почтовых соприкосновений."
        )
    if gmail_messages_available > len(messages):
        warnings.append(
            "Карта показывает только окно последних почтовых сообщений; счётчики внешних "
            "контактов, организаций и соприкосновений относятся к этому окну."
        )
    if external_rows:
        warnings.append(
            "Внешние люди и организации остаются кандидатами, пока участник команды "
            "не примет по ним решение."
        )

    return {
        "workspace_id": workspace_id,
        "mode": COMPANY_MAP_MODE,
        "source": COMPANY_MAP_SOURCE,
        "company": {
            "key": f"workspace:{workspace.id}",
            "workspace_id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "status": workspace.status,
            "source_refs": [
                {
                    "id": f"workspace:{workspace.id}",
                    "kind": "workspace",
                    "source": "founderos",
                    "label": workspace.name,
                    "url": None,
                    "record_type": "workspace",
                    "record_id": workspace.id,
                }
            ],
        },
        "summary": {
            "internal_people": len(internal_people),
            "external_contacts_in_window": len(external_rows),
            "organizations_in_window": len(organization_rows),
            "touchpoints_in_window": len(touchpoints),
            "confirmed_external_people": len(durable["confirmed_people"]),
            "confirmed_organizations": len(durable["confirmed_organizations"]),
        },
        "window": {
            "gmail_messages_available": gmail_messages_available,
            "gmail_messages_considered": len(messages),
            "message_limit": message_limit,
            "truncated": gmail_messages_available > len(messages),
            "order": "newest_first",
        },
        "people": {
            "internal": internal_people,
            "external_candidates": external_rows,
            "confirmed_external": durable["confirmed_people"],
        },
        "organizations": organization_rows,
        "confirmed_organizations": durable["confirmed_organizations"],
        "touchpoints": touchpoints,
        "capabilities": {
            "read_only": True,
            "can_resolve": access_role in {"owner", "admin", "member"},
            "required_role": "member",
            "provider_calls": False,
            "llm_used": False,
        },
        "warnings": warnings,
        "is_live": False,
        "llm_used": False,
    }


def _empty_durable_rows() -> dict[str, Any]:
    return {
        "confirmed_people": [],
        "confirmed_organizations": [],
        "resolved_candidates": set(),
        "confirmed_person_candidate_keys": set(),
        "confirmed_organization_candidate_keys": set(),
        "person_ids_by_user_id": {},
        "candidate_person_key_map": {},
        "candidate_organization_key_map": {},
    }


async def _resolution_only_company_world_rows(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    external_candidate_keys: set[str],
    organization_candidate_keys: set[str],
) -> dict[str, Any]:
    """Load only resolutions needed to filter the current bounded projection."""

    candidate_pairs = {("external_person", key) for key in external_candidate_keys} | {
        ("organization", key) for key in organization_candidate_keys
    }
    durable = _empty_durable_rows()
    if not candidate_pairs:
        return durable

    rows = (
        await session.execute(
            select(
                CompanyWorldResolution.candidate_type,
                CompanyWorldResolution.candidate_key,
            ).where(
                CompanyWorldResolution.workspace_id == workspace_id,
                tuple_(
                    CompanyWorldResolution.candidate_type,
                    CompanyWorldResolution.candidate_key,
                ).in_(sorted(candidate_pairs)),
            )
        )
    ).all()
    durable["resolved_candidates"] = {
        (candidate_type, candidate_key) for candidate_type, candidate_key in rows
    }
    if organization_candidate_keys:
        confirmed_organization_keys = (
            await session.execute(
                select(Organization.canonical_key).where(
                    Organization.workspace_id == workspace_id,
                    Organization.status == PROFILE_STATUS_ACTIVE,
                    Organization.canonical_key.in_(sorted(organization_candidate_keys)),
                )
            )
        ).scalars()
        durable["confirmed_organization_candidate_keys"] = set(confirmed_organization_keys)
    return durable


async def _durable_company_world_rows(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> dict[str, Any]:
    people = list(
        (
            await session.execute(
                select(Person).where(
                    Person.workspace_id == workspace_id,
                    Person.status == PROFILE_STATUS_ACTIVE,
                )
            )
        ).scalars()
    )
    organizations = list(
        (
            await session.execute(
                select(Organization).where(
                    Organization.workspace_id == workspace_id,
                    Organization.status == PROFILE_STATUS_ACTIVE,
                )
            )
        ).scalars()
    )
    affiliations = list(
        (
            await session.execute(
                select(Affiliation).where(
                    Affiliation.workspace_id == workspace_id,
                    Affiliation.status == PROFILE_STATUS_ACTIVE,
                )
            )
        ).scalars()
    )
    interactions = list(
        (
            await session.execute(
                select(Interaction).where(Interaction.workspace_id == workspace_id)
            )
        ).scalars()
    )
    resolutions = list(
        (
            await session.execute(
                select(CompanyWorldResolution).where(
                    CompanyWorldResolution.workspace_id == workspace_id
                )
            )
        ).scalars()
    )

    organizations_by_id = {organization.id: organization for organization in organizations}
    affiliations_by_person = {affiliation.person_id: affiliation for affiliation in affiliations}
    interactions_by_person: dict[UUID, list[Interaction]] = {}
    interactions_by_organization: dict[UUID, list[Interaction]] = {}
    for interaction in interactions:
        interactions_by_person.setdefault(interaction.person_id, []).append(interaction)
        if interaction.organization_id is not None:
            interactions_by_organization.setdefault(interaction.organization_id, []).append(
                interaction
            )

    resolutions_by_person = {
        resolution.result_person_id: resolution
        for resolution in resolutions
        if resolution.result_person_id is not None
    }
    resolutions_by_organization = {
        resolution.result_organization_id: resolution
        for resolution in resolutions
        if resolution.result_organization_id is not None
    }
    confirmed_people: list[dict[str, Any]] = []
    candidate_person_key_map: dict[str, str] = {}
    for person in people:
        if person.origin != PERSON_ORIGIN_FOUNDER_CONFIRMATION or person.user_id is not None:
            continue
        affiliation = affiliations_by_person.get(person.id)
        organization = (
            organizations_by_id.get(affiliation.organization_id)
            if affiliation is not None
            else None
        )
        person_interactions = interactions_by_person.get(person.id, [])
        resolution = resolutions_by_person.get(person.id)
        if resolution is not None:
            candidate_person_key_map[resolution.candidate_key] = f"person:{person.id}"
        confirmed_people.append(
            {
                "key": f"person:{person.id}",
                "person_id": person.id,
                "email": person.normalized_email,
                "display_name": person.display_name,
                "status": person.status,
                "organization_id": organization.id if organization else None,
                "organization_key": (f"organization:{organization.id}" if organization else None),
                "organization_name": organization.display_name if organization else None,
                "relationship_type": (affiliation.relationship_type if affiliation else None),
                "role_title": affiliation.role_title if affiliation else None,
                "interaction_count": len(person_interactions),
                "last_interaction_at": _latest_interaction_at(person_interactions),
                "source_refs": _durable_source_refs(
                    interactions=person_interactions,
                    resolution=resolution,
                    fallback_label=person.display_name or person.normalized_email,
                ),
            }
        )

    people_by_organization: dict[UUID, set[UUID]] = {}
    for affiliation in affiliations:
        people_by_organization.setdefault(affiliation.organization_id, set()).add(
            affiliation.person_id
        )
    confirmed_organizations: list[dict[str, Any]] = []
    candidate_organization_key_map: dict[str, str] = {}
    for organization in organizations:
        organization_interactions = interactions_by_organization.get(organization.id, [])
        resolution = resolutions_by_organization.get(organization.id)
        durable_key = f"organization:{organization.id}"
        candidate_organization_key_map[organization.canonical_key] = durable_key
        if resolution is not None and resolution.candidate_type == "organization":
            candidate_organization_key_map[resolution.candidate_key] = durable_key
        confirmed_organizations.append(
            {
                "key": f"organization:{organization.id}",
                "organization_id": organization.id,
                "domain": organization.normalized_domain,
                "name": organization.display_name,
                "relationship_kind": organization.relationship_kind,
                "status": organization.status,
                "people_count": len(people_by_organization.get(organization.id, set())),
                "interaction_count": len(organization_interactions),
                "last_interaction_at": _latest_interaction_at(organization_interactions),
                "source_refs": _durable_source_refs(
                    interactions=organization_interactions,
                    resolution=resolution,
                    fallback_label=organization.display_name,
                ),
            }
        )

    confirmed_people.sort(
        key=lambda row: (
            row["last_interaction_at"] or datetime.min.replace(tzinfo=timezone.utc),
            row["email"],
        ),
        reverse=True,
    )
    confirmed_organizations.sort(
        key=lambda row: (
            row["last_interaction_at"] or datetime.min.replace(tzinfo=timezone.utc),
            row["name"],
        ),
        reverse=True,
    )
    return {
        "confirmed_people": confirmed_people,
        "confirmed_organizations": confirmed_organizations,
        "resolved_candidates": {
            (resolution.candidate_type, resolution.candidate_key) for resolution in resolutions
        },
        "confirmed_person_candidate_keys": set(candidate_person_key_map),
        "confirmed_organization_candidate_keys": {
            organization.canonical_key for organization in organizations
        },
        "person_ids_by_user_id": {
            person.user_id: person.id for person in people if person.user_id is not None
        },
        "candidate_person_key_map": candidate_person_key_map,
        "candidate_organization_key_map": candidate_organization_key_map,
    }


def _latest_interaction_at(interactions: list[Interaction]) -> datetime | None:
    values = [interaction.occurred_at for interaction in interactions]
    return max(values) if values else None


def _durable_source_refs(
    *,
    interactions: list[Interaction],
    resolution: CompanyWorldResolution | None,
    fallback_label: str,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[UUID] = set()
    for interaction in sorted(
        interactions,
        key=lambda row: row.occurred_at,
        reverse=True,
    ):
        if interaction.source_record_id in seen:
            continue
        seen.add(interaction.source_record_id)
        refs.append(
            {
                "id": f"source-record:{interaction.source_record_id}",
                "kind": "gmail_message",
                "source": "gmail",
                "label": interaction.subject or fallback_label,
                "url": interaction.source_url,
                "record_type": "message",
                "record_id": interaction.source_record_id,
            }
        )
    if resolution is not None and resolution.source_record_id not in seen:
        refs.append(
            {
                "id": f"source-record:{resolution.source_record_id}",
                "kind": "gmail_message",
                "source": "gmail",
                "label": fallback_label,
                "url": None,
                "record_type": "message",
                "record_id": resolution.source_record_id,
            }
        )
    return refs


async def _gmail_message_count(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> int:
    count = await session.scalar(
        select(func.count(SourceRecord.id))
        .where(SourceRecord.workspace_id == workspace_id)
        .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL)
        .where(SourceRecord.record_type == "message")
        .where(SourceRecord.is_deleted.is_(False))
    )
    return int(count or 0)


async def _bounded_gmail_message_rows(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    limit: int,
) -> list[dict[str, Any]]:
    records = (
        await session.execute(
            select(SourceRecord)
            .where(
                SourceRecord.workspace_id == workspace_id,
                SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL,
                SourceRecord.record_type == "message",
                SourceRecord.is_deleted.is_(False),
            )
            .order_by(
                SourceRecord.source_updated_at.desc().nullslast(),
                SourceRecord.created_at.desc(),
                SourceRecord.id.desc(),
            )
            .limit(limit)
        )
    ).scalars()
    return [_gmail_message_payload(record) for record in records]


def _message_participant_emails(messages: list[Any]) -> set[str]:
    participant_emails: set[str] = set()
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        sender = _parse_mailbox(message.get("from_address"))
        if sender is not None:
            participant_emails.add(sender[1])
        participant_emails.update(
            email for _display_name, email in _mailboxes(message.get("to_addresses"))
        )
    return participant_emails


async def _matching_active_workspace_members(
    *,
    session: AsyncSession,
    workspace: Workspace,
    participant_emails: set[str],
) -> list[WorkspaceMembership]:
    if not participant_emails:
        return []
    rows = (
        await session.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.workspace_id == workspace.id,
                User.status == USER_STATUS_ACTIVE,
                User.email.in_(sorted(participant_emails)),
            )
            .order_by(Membership.created_at.asc(), User.email.asc())
        )
    ).all()
    return [
        WorkspaceMembership(user=user, workspace=workspace, membership=membership)
        for user, membership in rows
    ]


def _parse_mailbox(value: Any) -> tuple[str | None, str] | None:
    text = _safe_text(value)
    if text is None:
        return None
    display_name, address = parseaddr(text)
    email = _normalize_email(address or text)
    if "@" not in email:
        return None
    name = display_name.strip() or None
    return name, email


def _mailboxes(value: Any) -> list[tuple[str | None, str]]:
    values = value if isinstance(value, list) else []
    parsed = [_parse_mailbox(item) for item in values]
    return [mailbox for mailbox in parsed if mailbox is not None]


def _normalize_email(value: str) -> str:
    return value.strip().casefold()


def _external_person_key(email: str) -> str:
    digest = sha256(email.encode("utf-8")).hexdigest()[:20]
    return f"external-person:{digest}"


def _organization_key_for_email(email: str) -> str | None:
    domain = email.rsplit("@", maxsplit=1)[-1].casefold()
    if not domain or domain in GENERIC_EMAIL_DOMAINS or "." not in domain:
        return None
    return f"organization:{domain}"


def _direction(
    *,
    sender_email: str | None,
    recipient_emails: list[str],
    internal_emails: set[str],
) -> str:
    sender_internal = sender_email in internal_emails if sender_email else False
    recipients_internal = any(email in internal_emails for email in recipient_emails)
    recipients_external = any(email not in internal_emails for email in recipient_emails)
    if sender_internal and recipients_internal and recipients_external:
        return "mixed"
    if sender_internal and recipients_external:
        return "outbound"
    if sender_email and not sender_internal and recipients_internal:
        return "inbound"
    return "unknown"


def _source_refs(
    value: Any,
    *,
    canonical_source: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs = [dict(ref) for ref in value if isinstance(ref, Mapping)]
    if canonical_source is not None:
        for ref in refs:
            ref["source"] = canonical_source
    return refs


def _merge_source_refs(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [*existing]
    seen = {str(ref.get("id") or ref.get("record_id")) for ref in existing}
    for ref in incoming:
        key = str(ref.get("id") or ref.get("record_id"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return merged


async def _candidate_payload_hashes(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    candidates: list[Mapping[str, Any]],
) -> dict[UUID, str]:
    record_ids = {
        record_id
        for candidate in candidates
        for record_id in _candidate_source_record_ids(candidate)
    }
    if not record_ids:
        return {}
    rows = (
        await session.execute(
            select(SourceRecord.id, SourceRecord.payload_hash).where(
                SourceRecord.workspace_id == workspace_id,
                SourceRecord.id.in_(record_ids),
                SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL,
                SourceRecord.record_type == "message",
                SourceRecord.is_deleted.is_(False),
            )
        )
    ).all()
    return {record_id: payload_hash for record_id, payload_hash in rows}


def _candidate_source_record_ids(candidate: Mapping[str, Any]) -> list[UUID]:
    record_ids: set[UUID] = set()
    for ref in _source_refs(candidate.get("source_refs")):
        raw_id = ref.get("record_id")
        try:
            record_ids.add(UUID(str(raw_id)))
        except (TypeError, ValueError):
            continue
    return sorted(record_ids, key=str)


def _candidate_version(
    candidate: Mapping[str, Any],
    payload_hashes: Mapping[UUID, str],
) -> str:
    """Return a stable version over candidate identity and visible evidence."""

    visible_fields: dict[str, Any] = {}
    for field in (
        "key",
        "email",
        "display_name",
        "organization_key",
        "domain",
        "name",
        "kind",
        "people_count",
        "interaction_count",
        "last_interaction_at",
    ):
        value = candidate.get(field)
        visible_fields[field] = value.isoformat() if isinstance(value, datetime) else value
    visible_fields["source_records"] = [
        {
            "id": str(record_id),
            "payload_hash": payload_hashes.get(record_id, ""),
        }
        for record_id in _candidate_source_record_ids(candidate)
    ]
    material = json.dumps(
        visible_fields,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _datetime_or_none(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _latest_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _subject_or_fallback(value: Any) -> str:
    subject = _safe_text(value)
    if subject is None or subject.casefold() in {"(no subject)", "no subject"}:
        return "Без темы"
    return subject


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and text.startswith(("https://", "http://")) and "@" not in text:
        return text[:1000]
    return None
