"""Email thread agent: communication signals from stored gmail threads.

Reads persisted ``email_thread_states`` (rebuilt from stored messages,
no provider calls) and emits ``communication_silence`` findings:

- an inbound thread waiting for MY reply for >= 3 days (strong signal);
- a thread where the other side is silent for >= 7 days after our
  message (weaker signal — below the confidence threshold it lands in
  the inbox as a proposal instead of a finding).

Everything is founder-scope: raw communication never leaks to team or
investor views.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.gmail_models import EmailThreadState
from app.services.confidence import build_confidence
from app.services.second_opinion import (
    FINDING_COMMUNICATION_SILENCE,
    emit_finding_or_proposal,
)

AGENT_NAME = "email_thread_agent"

NEEDS_REPLY_MIN_DAYS = 3
EXTERNAL_SILENCE_MIN_DAYS = 7

_STATUS_NEEDS_MY_REPLY = "needs_my_reply"
_STATUS_WAITING_EXTERNAL = "waiting_for_external_reply"


def _freshness(last_message_at: datetime | None, now: datetime) -> float:
    if last_message_at is None:
        return 0.3
    age_days = max(0.0, (now - last_message_at).total_seconds() / 86400.0)
    return max(0.1, min(1.0, 1.0 - age_days / 30.0))


async def scan_email_silence(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    safe_now = now or datetime.now(timezone.utc)
    # defaultdict so the full set of upsert/emit outcomes
    # (created / updated_new_evidence / updated_clock / unchanged /
    # reopened / skipped / proposed / proposal_exists / no_evidence)
    # never KeyErrors as the taxonomy grows.
    counts: dict[str, int] = defaultdict(int)

    threads = (
        await session.execute(
            select(EmailThreadState).where(
                EmailThreadState.status.in_(
                    [_STATUS_NEEDS_MY_REPLY, _STATUS_WAITING_EXTERNAL]
                )
            )
        )
    ).scalars()

    for thread in threads:
        days = int(thread.days_without_reply or 0)
        subject = thread.subject_display or thread.subject_normalized or "без темы"
        evidence = [
            {
                "kind": "email_thread_state",
                "thread_key": thread.thread_key,
                "subject": subject[:200],
                "status": thread.status,
                "last_message_at": (
                    thread.last_message_at.isoformat()
                    if thread.last_message_at
                    else None
                ),
                "last_message_from": thread.last_message_from,
                "days_without_reply": days,
            }
        ]

        if thread.status == _STATUS_NEEDS_MY_REPLY:
            if days < NEEDS_REPLY_MIN_DAYS:
                continue
            score, factors = build_confidence(
                evidence_count=2,
                source_quality=0.8,
                freshness=_freshness(thread.last_message_at, safe_now),
                cross_source_match=False,
            )
            outcome = await emit_finding_or_proposal(
                session,
                agent=AGENT_NAME,
                finding_kwargs={
                    "finding_key": f"email:{thread.thread_key}:needs_my_reply",
                    "entity_id": None,
                    "finding_type": FINDING_COMMUNICATION_SILENCE,
                    "declared_state": "Входящее письмо ждёт моего ответа",
                    "observed_state": f"Без ответа {days} дн",
                    "summary": f"Ждёт ответа: {subject[:140]}",
                    "severity": "high" if days >= 7 else "medium",
                    "confidence": score,
                    "confidence_factors": factors,
                    "evidence_refs": evidence,
                    "source_refs": [{"kind": "gmail_thread", "thread_key": thread.thread_key}],
                    "visibility_scope": "founder",
                },
            )
            counts[outcome] += 1
            continue

        if days < EXTERNAL_SILENCE_MIN_DAYS:
            continue
        score, factors = build_confidence(
            evidence_count=1,
            source_quality=0.7,
            freshness=_freshness(thread.last_message_at, safe_now),
            cross_source_match=False,
        )
        outcome = await emit_finding_or_proposal(
            session,
            agent=AGENT_NAME,
            finding_kwargs={
                "finding_key": f"email:{thread.thread_key}:external_silence",
                "entity_id": None,
                "finding_type": FINDING_COMMUNICATION_SILENCE,
                "declared_state": "Мы написали и ждём ответа собеседника",
                "observed_state": f"Собеседник молчит {days} дн",
                "summary": f"Тишина в треде: {subject[:140]}",
                "severity": "medium" if days >= 14 else "low",
                "confidence": score,
                "confidence_factors": factors,
                "evidence_refs": evidence,
                "source_refs": [{"kind": "gmail_thread", "thread_key": thread.thread_key}],
                "visibility_scope": "founder",
            },
        )
        counts[outcome] += 1

    return counts
