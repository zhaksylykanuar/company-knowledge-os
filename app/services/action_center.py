"""Action Center: one ranked "what to do next" layer.

Aggregates recommendations from second-opinion findings, graph gardener
proposals, stale/ownerless/blocked tasks, sales relationship signals,
product validation gaps and data-availability problems into a single
list. Each action carries its source and the reference needed for its
CTA, which routes to the existing decision endpoints — the Action
Center never mutates anything itself. AI proposes; the human confirms.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.second_opinion_models import SecondOpinionFinding
from app.services.data_availability import get_availability
from app.services.execution_view import build_execution_view
from app.services.inbox import build_inbox
from app.services.sales_view import build_sales_signals
from app.services.second_opinion import _finding_read_model

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _action(
    *,
    title: str,
    why_now: str,
    affected_entity: str | None,
    evidence_count: int,
    severity: str,
    confidence: float | None,
    source: str,
    action_type: str,
    cta: str,
    action_ref: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": title,
        "why_now": why_now,
        "affected_entity": affected_entity,
        "evidence_count": evidence_count,
        "severity": severity,
        "confidence": confidence,
        "source": source,
        "action_type": action_type,
        "cta": cta,
        "action_ref": action_ref,
    }


async def build_action_center(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    actions: list[dict[str, Any]] = []

    # 1. Second opinion findings (open).
    finding_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == "open")
            .where(
                (SecondOpinionFinding.snoozed_until.is_(None))
                | (SecondOpinionFinding.snoozed_until <= safe_now)
            )
            .limit(60)
        )
    ).scalars()
    for row in finding_rows:
        f = _finding_read_model(row)
        actions.append(
            _action(
                title=f["summary"],
                why_now=f["observed_state"],
                affected_entity=f["entity_id"],
                evidence_count=len(f.get("evidence_refs") or []),
                severity=f["severity"],
                confidence=f["confidence"],
                source="second_opinion",
                action_type="resolve_conflict",
                cta=f.get("suggested_action") or "Разобрать конфликт",
                action_ref={"kind": "finding", "finding_key": f["finding_key"]},
            )
        )

    # 2. Graph gardener proposals (pending hygiene decisions).
    inbox = await build_inbox(session, limit=60)
    for proposal in inbox.get("gardener_proposals", []):
        actions.append(
            _action(
                title=proposal["title"],
                why_now=proposal.get("why") or "Гигиена графа знаний",
                affected_entity=(proposal.get("payload") or {}).get("entity_id"),
                evidence_count=len(proposal.get("evidence_refs") or []),
                severity="low",
                confidence=proposal.get("confidence"),
                source="graph_gardener",
                action_type="review_hygiene",
                cta="Решить в Inbox",
                action_ref={"kind": "proposal", "proposal_id": proposal["proposal_id"]},
            )
        )

    # 3. Execution: stale / ownerless / blocked / overdue tasks.
    execution = await build_execution_view(session, now=safe_now)
    for bucket, action_type, cta, sev in (
        ("blocked_quests", "unblock_task", "Разблокировать", "high"),
        ("overdue_quests", "renegotiate_deadline", "Передоговорить срок", "high"),
        ("ownerless_quests", "assign_owner", "Назначить ответственного", "medium"),
        ("stale_quests", "refresh_task", "Обновить или закрыть", "medium"),
    ):
        for quest in execution.get(bucket, [])[:5]:
            actions.append(
                _action(
                    title=f"[{quest['issue_key']}] {quest['title'][:120]}",
                    why_now=", ".join(quest["flags"]),
                    affected_entity=quest.get("project"),
                    evidence_count=quest.get("evidence_count", 0),
                    severity=sev,
                    confidence=None,
                    source="execution",
                    action_type=action_type,
                    cta=cta,
                    action_ref={"kind": "task", "issue_key": quest["issue_key"]},
                )
            )

    # 4. Sales relationship signals.
    sales = await build_sales_signals(session)
    for account in sales.get("accounts", []):
        for signal in account.get("signals", []):
            actions.append(
                _action(
                    title=signal["summary"],
                    why_now=signal["observed_state"],
                    affected_entity=account.get("client_id"),
                    evidence_count=len(signal.get("evidence_refs") or []),
                    severity=signal["severity"],
                    confidence=signal["confidence"],
                    source="sales",
                    action_type="reengage_account",
                    cta=signal.get("suggested_action") or "Написать контакту",
                    action_ref={"kind": "finding", "finding_key": signal["finding_key"]},
                )
            )

    # 5. Data availability problems (stale / no_data series).
    availability = await get_availability(session)
    for row in availability:
        if row["status"] in {"stale", "no_data"}:
            actions.append(
                _action(
                    title=f"Данные: {row['metric_key']} ({row['scope']})",
                    why_now=row["message"],
                    affected_entity=row["scope"],
                    evidence_count=row["points_count"],
                    severity="low",
                    confidence=None,
                    source="data_availability",
                    action_type="refresh_data",
                    cta="Прогнать агентов / синк",
                    action_ref={"kind": "metric", "metric_key": row["metric_key"]},
                )
            )

    actions.sort(
        key=lambda a: (
            _SEVERITY_RANK.get(a["severity"], 3),
            -(a["evidence_count"] or 0),
        )
    )

    by_source: dict[str, int] = {}
    for a in actions:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1

    return {
        "generated_at": safe_now.isoformat(),
        "actions": actions[:limit],
        "counts": {"total": len(actions), "by_source": by_source},
    }
