"""Sales signal agent: relationship state from communication, no finance.

Builds the sales graph from stored email threads (and is ready to fold in
meetings/tasks): companies become ``client`` nodes, external participants
become ``person`` contacts ``employed_by`` the company, and each account
relationship becomes a ``deal`` signal-entity ``belongs_to`` the company.
``deal`` here is a *signal* entity — never a money amount, never a
pipeline. Warmth is an observed attribute, not a guess.

Findings (account-level, founder-scoped, evidence-required): a previously
two-way-active account that has gone silent past a threshold is a
relationship risk surfaced as ``communication_silence``. Weak signals go
to the inbox as proposals, never silently into the feed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.gmail_models import EmailThreadState
from app.services.confidence import build_confidence
from app.services.email_threads import (
    _sender_domain,
    normalize_email_address,
    parse_email_addresses,
    parse_email_me_addresses,
)
from app.services.knowledge_graph import (
    ENTITY_CLIENT,
    ENTITY_DEAL,
    ENTITY_PERSON,
    REL_BELONGS_TO,
    REL_EMPLOYED_BY,
    slugify,
    upsert_alias,
    upsert_entity,
    upsert_link,
)
from app.services.second_opinion import (
    FINDING_COMMUNICATION_SILENCE,
    emit_finding_or_proposal,
)

AGENT_NAME = "sales_signal_agent"

# Domains that are mailbox providers, not companies.
_FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
        "mail.ru",
        "yandex.ru",
        "proton.me",
        "protonmail.com",
        "qq.com",
    }
)

WARMTH_WINDOW_DAYS = 14
RELATIONSHIP_RISK_MIN_DAYS = 10
MIN_MESSAGES_FOR_ACCOUNT_SIGNAL = 2


def _is_company_domain(domain: str | None, my_domains: set[str]) -> bool:
    if not domain or domain in _FREE_EMAIL_DOMAINS or domain in my_domains:
        return False
    return "." in domain


def _warmth(last_message_at: datetime | None, now: datetime) -> str:
    if last_message_at is None:
        return "unknown"
    age_days = (now - last_message_at).total_seconds() / 86400.0
    if age_days <= WARMTH_WINDOW_DAYS:
        return "warm"
    if age_days <= WARMTH_WINDOW_DAYS * 3:
        return "cooling"
    return "cold"


def _external_company_addresses(
    thread: EmailThreadState, my_addresses: set[str], my_domains: set[str]
) -> list[str]:
    addresses = set(parse_email_addresses(thread.participants_json or []))
    sender = normalize_email_address(thread.last_message_from)
    if sender:
        addresses.add(sender)
    out: list[str] = []
    for address in sorted(addresses):
        if address in my_addresses:
            continue
        if _is_company_domain(_sender_domain(address), my_domains):
            out.append(address)
    return out


async def scan_sales_signals(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    safe_now = now or datetime.now(timezone.utc)
    counts = {
        "accounts": 0,
        "contacts": 0,
        "signals": 0,
        "links_created": 0,
        "findings": 0,
        "proposals": 0,
    }

    my_addresses = parse_email_me_addresses()
    my_domains = {
        domain
        for addr in my_addresses
        if (domain := _sender_domain(addr)) is not None
    }

    threads = list(
        (await session.execute(select(EmailThreadState))).scalars()
    )

    # Aggregate per company domain across threads.
    accounts: dict[str, dict[str, Any]] = {}
    for thread in threads:
        for address in _external_company_addresses(
            thread, my_addresses, my_domains
        ):
            domain = _sender_domain(address)
            if domain is None:
                continue
            bucket = accounts.setdefault(
                domain,
                {
                    "contacts": set(),
                    "threads": [],
                    "last_message_at": None,
                    "messages": 0,
                },
            )
            bucket["contacts"].add(address)
            bucket["threads"].append(thread)
            bucket["messages"] += int(thread.messages_count or 1)
            if thread.last_message_at is not None and (
                bucket["last_message_at"] is None
                or thread.last_message_at > bucket["last_message_at"]
            ):
                bucket["last_message_at"] = thread.last_message_at

    for domain, bucket in accounts.items():
        client_id = f"client:{slugify(domain)}"
        warmth = _warmth(bucket["last_message_at"], safe_now)
        if await upsert_entity(
            session,
            entity_id=client_id,
            entity_type=ENTITY_CLIENT,
            canonical_name=domain,
            attrs={
                "domain": domain,
                "warmth": warmth,
                "messages_seen": bucket["messages"],
                "last_message_at": (
                    bucket["last_message_at"].isoformat()
                    if bucket["last_message_at"]
                    else None
                ),
            },
        ):
            counts["accounts"] += 1
        await upsert_alias(
            session, entity_id=client_id, alias=domain, source="email_domain"
        )

        deal_id = f"deal:{slugify(domain)}"
        if await upsert_entity(
            session,
            entity_id=deal_id,
            entity_type=ENTITY_DEAL,
            canonical_name=f"Отношения: {domain}",
            attrs={"warmth": warmth, "account": domain},
        ):
            counts["signals"] += 1
        if await upsert_link(
            session,
            from_entity_id=deal_id,
            relation=REL_BELONGS_TO,
            to_entity_id=client_id,
            evidence_refs=[{"kind": "email_account", "domain": domain}],
            confidence=0.8,
        ):
            counts["links_created"] += 1

        for address in sorted(bucket["contacts"]):
            contact_id = f"person:{slugify(address)}"
            if await upsert_entity(
                session,
                entity_id=contact_id,
                entity_type=ENTITY_PERSON,
                canonical_name=address,
                attrs={"email": address, "external": True},
            ):
                counts["contacts"] += 1
            await upsert_alias(
                session,
                entity_id=contact_id,
                alias=address,
                source="email_contact",
            )
            if await upsert_link(
                session,
                from_entity_id=contact_id,
                relation=REL_EMPLOYED_BY,
                to_entity_id=client_id,
                evidence_refs=[{"kind": "email_participant", "address": address}],
                confidence=0.75,
            ):
                counts["links_created"] += 1

        # Relationship risk: a two-way-active account now gone silent.
        if (
            bucket["messages"] >= MIN_MESSAGES_FOR_ACCOUNT_SIGNAL
            and warmth in {"cooling", "cold"}
            and bucket["last_message_at"] is not None
        ):
            silent_days = int(
                (safe_now - bucket["last_message_at"]).total_seconds() / 86400.0
            )
            if silent_days >= RELATIONSHIP_RISK_MIN_DAYS:
                score, factors = build_confidence(
                    evidence_count=min(len(bucket["threads"]), 4),
                    source_quality=0.7,
                    freshness=0.3,
                    cross_source_match=False,
                )
                outcome = await emit_finding_or_proposal(
                    session,
                    agent=AGENT_NAME,
                    finding_kwargs={
                        "finding_key": f"{deal_id}:relationship_risk",
                        "entity_id": deal_id,
                        "finding_type": FINDING_COMMUNICATION_SILENCE,
                        "declared_state": (
                            f"Аккаунт {domain}: были активные переписки "
                            f"({bucket['messages']} сообщений)"
                        ),
                        "observed_state": (
                            f"Тишина {silent_days} дн, отношения {warmth}"
                        ),
                        "summary": f"Отношения остывают: {domain}",
                        "severity": "medium" if silent_days >= 21 else "low",
                        "confidence": score,
                        "confidence_factors": factors,
                        "evidence_refs": [
                            {
                                "kind": "email_thread",
                                "thread_key": thread.thread_key,
                                "subject": thread.subject_display,
                            }
                            for thread in bucket["threads"][:3]
                        ],
                        "source_refs": [
                            {"kind": "email_account", "domain": domain}
                        ],
                        "visibility_scope": "founder",
                    },
                )
                if outcome in {"created", "updated_new_evidence", "reopened"}:
                    counts["findings"] += 1
                elif outcome == "proposed":
                    counts["proposals"] += 1

    return counts
