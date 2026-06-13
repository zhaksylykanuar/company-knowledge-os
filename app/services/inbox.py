"""Inbox read model: everything that waits for the founder's decision.

A decision center, not a list: each item carries why the AI thinks so
(confidence factors + hint), what it saw (source_snapshot, evidence)
and what happens on accept (consequences).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityLinkRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.agent_proposals import (
    STATUS_ACCEPTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    decide_proposal,
    list_proposals,
)
from app.services.confidence import explain_confidence
from app.services.entity_identity import KIND_ENTITY_MERGE, apply_decided_merges
from app.services.graph_tree import list_disputed_links
from app.services.second_opinion import STATUS_OPEN as FINDING_OPEN
from app.services.second_opinion import list_findings

_CONSEQUENCES = {
    KIND_ENTITY_MERGE: (
        "Ноды будут объединены: связи и алиасы дубликата перейдут к "
        "основной ноде, активность сольётся в один профиль. Обратимо."
    ),
    "graph_orphan_node": (
        "Нода помечается как проверенная. Удаление не выполняется "
        "автоматически — только пометка для последующей чистки."
    ),
    "graph_node_without_evidence": (
        "Нода без источника помечается на ревью. Молчаливого удаления нет."
    ),
    "graph_edge_without_evidence": (
        "Связь без evidence помечается на ревью; удаление — отдельным шагом."
    ),
    "graph_duplicate_account": (
        "Аккаунты помечаются как кандидаты на объединение. Слияние "
        "произойдёт только после отдельного подтверждения."
    ),
    "finding_lost_evidence": (
        "Finding без evidence будет закрыт как недоказуемый."
    ),
    "finding_suggestion": (
        "Слабый сигнал станет полноценным finding в ленте Second Opinion."
    ),
}

# Why each gardener problem matters — shown on the card.
_GARDENER_WHY = {
    "graph_orphan_node": (
        "Изолированная нода ни с чем не связана — она либо мусор, либо "
        "у неё потеряны связи. Искажает граф и second opinion."
    ),
    "graph_node_without_evidence": (
        "У ноды нет источника (аккаунта/алиаса) — невозможно доказать, "
        "что сущность реальна."
    ),
    "graph_edge_without_evidence": (
        "Связь без evidence — это утверждение без доказательства."
    ),
    "graph_duplicate_account": (
        "Один аккаунт как две ноды искажает warmth и histor."
    ),
    "finding_lost_evidence": (
        "Открытый finding без evidence нарушает правило «нет evidence — "
        "нет вывода»."
    ),
}

GARDENER_KINDS = frozenset(_GARDENER_WHY) | {"graph_duplicate_account"}


def _is_gardener(proposal_type: str) -> bool:
    return proposal_type.startswith("graph_") or proposal_type == "finding_lost_evidence"


async def _merge_consequences(
    session: AsyncSession, payload: dict[str, Any]
) -> str:
    merge_id = str(payload.get("merge") or "")
    if not merge_id:
        return _CONSEQUENCES[KIND_ENTITY_MERGE]
    links = (
        await session.execute(
            select(func.count())
            .select_from(EntityLinkRecord)
            .where(
                (EntityLinkRecord.from_entity_id == merge_id)
                | (EntityLinkRecord.to_entity_id == merge_id)
            )
        )
    ).scalar() or 0
    return (
        f"Связей будет перевешено: {links}. " + _CONSEQUENCES[KIND_ENTITY_MERGE]
    )


async def build_inbox(session: AsyncSession, *, limit: int = 100) -> dict[str, Any]:
    proposals = await list_proposals(session, status=STATUS_PENDING, limit=limit)
    identity_proposals: list[dict[str, Any]] = []
    gardener_proposals: list[dict[str, Any]] = []
    for proposal in proposals:
        proposal["confidence_hint"] = explain_confidence(
            proposal["confidence"], proposal.get("confidence_factors") or {}
        )
        ptype = proposal["proposal_type"]
        if ptype == KIND_ENTITY_MERGE:
            proposal["consequences"] = await _merge_consequences(
                session, proposal.get("payload") or {}
            )
        else:
            proposal["consequences"] = _CONSEQUENCES.get(
                ptype, "Изменение графа знаний."
            )
        proposal["why"] = _GARDENER_WHY.get(ptype, "")
        proposal["reject_note"] = (
            "Reject фиксирует решение по стабильному ключу — то же "
            "предложение не всплывёт снова без нового evidence."
        )
        if _is_gardener(ptype):
            gardener_proposals.append(proposal)
        else:
            identity_proposals.append(proposal)

    findings = await list_findings(session, status=FINDING_OPEN, limit=50)
    disputed = await list_disputed_links(session)

    open_findings_total = (
        await session.execute(
            select(func.count())
            .select_from(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == FINDING_OPEN)
        )
    ).scalar() or 0

    return {
        "proposals": proposals,
        "identity_proposals": identity_proposals,
        "gardener_proposals": gardener_proposals,
        "findings": findings,
        "disputed_links": disputed,
        "counts": {
            "proposals": len(proposals),
            "identity_proposals": len(identity_proposals),
            "gardener_proposals": len(gardener_proposals),
            "findings_open": int(open_findings_total),
            "disputed_links": len(disputed),
            "total": len(proposals) + int(open_findings_total) + len(disputed),
        },
    }


async def decide_inbox_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    decision: str,
    reviewer_id: str,
    decision_reason: str | None = None,
) -> dict[str, Any] | None:
    """Decide, immediately apply (merges repoint links) and audit."""

    from app.services.inbox_audit import (
        ACTION_PROPOSAL_DECISION,
        record_inbox_action,
    )

    if decision not in {STATUS_ACCEPTED, STATUS_REJECTED}:
        raise ValueError("decision must be accepted or rejected")
    decided = await decide_proposal(
        session,
        proposal_id=proposal_id,
        decision=decision,
        reviewer_id=reviewer_id,
        decision_reason=decision_reason,
    )
    if decided is None:
        return None
    applied = await apply_decided_merges(session)
    await record_inbox_action(
        session,
        action=ACTION_PROPOSAL_DECISION,
        actor=reviewer_id,
        target_id=proposal_id,
        previous_state={"status": "pending"},
        next_state={"status": decision, "applied": applied},
        reversible=True,
        details={"decision_reason": decision_reason},
    )
    return {**decided, "applied": applied}
