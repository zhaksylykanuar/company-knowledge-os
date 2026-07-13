from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parseaddr
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GMAIL, SourceRecord
from app.db.identity_models import Workspace
from app.services.company_brain_github_read_service import build_workspace_company_brain
from app.services.identity_service import list_workspace_members

COMPANY_MAP_MODE = "evidence_backed_projection"
COMPANY_MAP_SOURCE = "workspace_and_company_brain_projection"

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
) -> dict[str, Any]:
    """Build a read-only, evidence-backed map of people and organizations.

    The projection deliberately labels external people and email-domain
    organizations as candidates. It never infers that somebody is an employee,
    customer, decision maker, or account owner without founder confirmation.
    """

    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace not found")

    memberships = await list_workspace_members(session, workspace_id=workspace_id)
    brain = await build_workspace_company_brain(
        session=session,
        workspace_id=workspace_id,
        limit=limit,
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

    communications = brain.get("communications")
    raw_messages = (
        communications.get("messages", [])
        if isinstance(communications, Mapping)
        else []
    )
    messages = raw_messages if isinstance(raw_messages, list) else []

    for raw_message in messages:
        if not isinstance(raw_message, Mapping):
            continue
        sender = _parse_mailbox(raw_message.get("from_address"))
        recipients = _mailboxes(raw_message.get("to_addresses"))
        participants = [mailbox for mailbox in [sender, *recipients] if mailbox]
        participant_by_email = {mailbox[1]: mailbox for mailbox in participants}
        external_mailboxes = [
            mailbox
            for email, mailbox in participant_by_email.items()
            if email not in internal_keys
        ]

        source_refs = _source_refs(raw_message.get("source_refs"))
        occurred_at = _datetime_or_none(raw_message.get("received_at"))
        person_keys = [
            internal_keys[email]
            if email in internal_keys
            else _external_person_key(email)
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
                "subject": _safe_text(raw_message.get("subject")) or "(no subject)",
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
            person["source_refs"] = _merge_source_refs(
                person["source_refs"], source_refs
            )

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
            "Внешние люди и организации остаются кандидатами, пока основатель не "
            "подтвердит их роль."
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
        },
        "window": {
            "gmail_messages_available": gmail_messages_available,
            "gmail_messages_considered": len(messages),
            "message_limit": limit,
            "truncated": gmail_messages_available > len(messages),
            "order": "newest_first",
        },
        "people": {
            "internal": internal_people,
            "external_candidates": external_rows,
        },
        "organizations": organization_rows,
        "touchpoints": touchpoints,
        "capabilities": {
            "read_only": True,
            "provider_calls": False,
            "llm_used": False,
        },
        "warnings": warnings,
        "is_live": False,
        "llm_used": False,
    }


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


def _source_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(ref) for ref in value if isinstance(ref, Mapping)]


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


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and text.startswith(("https://", "http://")) and "@" not in text:
        return text[:1000]
    return None
