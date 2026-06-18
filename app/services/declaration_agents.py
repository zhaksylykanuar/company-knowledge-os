"""Agents that verify founder declarations against stored reality.

- hypothesis agent: a hypothesis declared validated must have supporting
  evidence in the knowledge base (``validation_gap`` otherwise); stored
  risks that share the hypothesis vocabulary produce
  ``evidence_contradiction`` findings with ``refutes`` graph links.
- focus drift: the declared weekly focus is compared with the actual
  7-day activity distribution across projects (``focus_drift``).

No declaration — no findings. No evidence — no findings.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import NormalizedActivityItemRecord
from app.db.source_models import DocumentChunk
from app.db.task_models import ExtractedRisk
from app.services.confidence import build_confidence
from app.services.declarations import KEY_FOCUS, KEY_HYPOTHESES, get_declaration
from app.services.entity_resolution import (
    ENTITY_TYPE_PROJECT,
    resolve_entities_in_text,
)
from app.services.jira_graph_mapping import all_mapped_jira_keys
from app.services.knowledge_graph import (
    ENTITY_HYPOTHESIS,
    REL_REFUTES,
    slugify,
    upsert_entity,
    upsert_link,
)
from app.services.second_opinion import (
    FINDING_EVIDENCE_CONTRADICTION,
    FINDING_FOCUS_DRIFT,
    FINDING_VALIDATION_GAP,
    emit_finding_or_proposal,
    outcome_emitted_finding,
)

AGENT_NAME = "declaration_agents"

_WORD_RE = re.compile(r"[\w-]{4,}", re.UNICODE)
_STOPWORDS = {
    "что", "это", "если", "когда", "будет", "может", "нужно", "после",
    "this", "that", "with", "будут", "через", "наша", "наши", "клиент",
}

FOCUS_MIN_ATTRIBUTED_EVENTS = 10
FOCUS_SHARE_THRESHOLD = 0.3
OTHER_SHARE_THRESHOLD = 0.5


def _tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in _WORD_RE.findall(str(text).casefold()):
        if token in _STOPWORDS or token in seen:
            continue
        seen.append(token)
    return seen[:6]


async def scan_hypotheses(session: AsyncSession) -> dict[str, int]:
    counts = {"hypotheses": 0, "findings": 0, "proposals": 0, "links_created": 0}
    declaration = await get_declaration(session, key=KEY_HYPOTHESES)
    items = (declaration or {}).get("payload", {}).get("items") or []

    for item in items:
        text = str(item.get("text") or "").strip()
        declared_status = str(item.get("status") or "testing")
        if not text:
            continue
        tokens = _tokens(text)
        if len(tokens) < 2:
            continue
        counts["hypotheses"] += 1

        hypothesis_id = f"hypothesis:{slugify(text)[:80]}"
        await upsert_entity(
            session,
            entity_id=hypothesis_id,
            entity_type=ENTITY_HYPOTHESIS,
            canonical_name=text[:255],
            attrs={"declared_status": declared_status},
        )

        token_filters = [
            DocumentChunk.text.ilike(f"%{token}%") for token in tokens[:4]
        ]
        supports = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(or_(*token_filters))
                )
            ).scalar()
            or 0
        )

        risk_filters = [
            ExtractedRisk.title.ilike(f"%{token}%") for token in tokens[:4]
        ]
        contradicting = list(
            (
                await session.execute(
                    select(ExtractedRisk).where(or_(*risk_filters)).limit(5)
                )
            ).scalars()
        )

        if declared_status == "validated" and supports == 0:
            score, factors = build_confidence(
                evidence_count=2,
                source_quality=0.8,
                freshness=0.8,
                cross_source_match=False,
            )
            outcome = await emit_finding_or_proposal(
                session,
                agent=AGENT_NAME,
                finding_kwargs={
                    "finding_key": f"{hypothesis_id}:validation_gap",
                    "entity_id": hypothesis_id,
                    "finding_type": FINDING_VALIDATION_GAP,
                    "declared_state": f"Гипотеза заявлена validated: «{text[:140]}»",
                    "observed_state": (
                        "В базе знаний нет подтверждающего evidence "
                        f"(поиск по: {', '.join(tokens[:4])})"
                    ),
                    "summary": f"Гипотеза без подтверждения: {text[:120]}",
                    "severity": "medium",
                    "confidence": score,
                    "confidence_factors": factors,
                    "evidence_refs": [
                        {"kind": "declaration", "status": declared_status},
                        {
                            "kind": "knowledge_search",
                            "tokens": tokens[:4],
                            "matches": supports,
                        },
                    ],
                    "source_refs": [{"kind": "declaration", "key": KEY_HYPOTHESES}],
                },
            )
            if outcome == "proposed":
                counts["proposals"] += 1
            elif outcome_emitted_finding(outcome):
                counts["findings"] += 1

        if contradicting:
            for risk in contradicting:
                if await upsert_link(
                    session,
                    from_entity_id=f"risk:{risk.id}",
                    relation=REL_REFUTES,
                    to_entity_id=hypothesis_id,
                    evidence_refs=[
                        {"kind": "extracted_risk", "risk_id": risk.id,
                         "title": risk.title[:200]}
                    ],
                    confidence=0.6,
                ):
                    counts["links_created"] += 1
            score, factors = build_confidence(
                evidence_count=len(contradicting),
                source_quality=0.7,
                freshness=0.7,
                cross_source_match=False,
                contradiction_strength=0.0,
            )
            outcome = await emit_finding_or_proposal(
                session,
                agent=AGENT_NAME,
                finding_kwargs={
                    "finding_key": f"{hypothesis_id}:evidence_contradiction",
                    "entity_id": hypothesis_id,
                    "finding_type": FINDING_EVIDENCE_CONTRADICTION,
                    "declared_state": (
                        f"Гипотеза ({declared_status}): «{text[:140]}»"
                    ),
                    "observed_state": (
                        "Сохранённые риски противоречат заявлению: "
                        + "; ".join(r.title[:80] for r in contradicting[:2])
                    ),
                    "summary": f"Evidence против гипотезы: {text[:120]}",
                    "severity": "medium",
                    "confidence": score,
                    "confidence_factors": factors,
                    "evidence_refs": [
                        {
                            "kind": "extracted_risk",
                            "risk_id": risk.id,
                            "source_id": f"risk:{risk.id}",
                            "title": risk.title[:200],
                        }
                        for risk in contradicting
                    ],
                    "source_refs": [{"kind": "declaration", "key": KEY_HYPOTHESES}],
                },
            )
            if outcome == "proposed":
                counts["proposals"] += 1
            elif outcome_emitted_finding(outcome):
                counts["findings"] += 1

    return counts


async def scan_focus_drift(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    counts = {"findings": 0, "proposals": 0, "skipped": 1}
    declaration = await get_declaration(session, key=KEY_FOCUS)
    focus = (declaration or {}).get("payload") or {}
    title = str(focus.get("title") or "").strip()
    if not title:
        return counts

    try:
        recognized = await resolve_entities_in_text(
            session, title, entity_type=ENTITY_TYPE_PROJECT
        )
    except Exception:
        recognized = []
    if not recognized:
        return counts
    focus_project = recognized[0].entity_id

    safe_now = now or datetime.now(timezone.utc)
    window_start = safe_now - timedelta(days=7)
    key_to_project = await all_mapped_jira_keys(session)

    occurred = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    rows = (
        await session.execute(
            select(NormalizedActivityItemRecord).where(occurred >= window_start)
        )
    ).scalars()

    per_project: dict[str, int] = {}
    for row in rows:
        projects: set[str] = set()
        for key in row.related_jira_keys or []:
            prefix = str(key).split("-")[0]
            if prefix in key_to_project:
                projects.add(key_to_project[prefix])
        if row.project and str(row.project) in key_to_project.values():
            projects.add(str(row.project))
        for project in projects:
            per_project[project] = per_project.get(project, 0) + 1

    total = sum(per_project.values())
    if total < FOCUS_MIN_ATTRIBUTED_EVENTS:
        return counts

    focus_count = per_project.get(focus_project, 0)
    focus_share = focus_count / total
    top_project, top_count = max(per_project.items(), key=lambda pair: pair[1])
    top_share = top_count / total

    counts["skipped"] = 0
    if focus_share >= FOCUS_SHARE_THRESHOLD or top_project == focus_project:
        return counts
    if top_share < OTHER_SHARE_THRESHOLD:
        return counts

    score, factors = build_confidence(
        evidence_count=min(total, 4),
        source_quality=0.8,
        freshness=0.9,
        cross_source_match=len(per_project) > 1,
    )
    outcome = await emit_finding_or_proposal(
        session,
        agent=AGENT_NAME,
        finding_kwargs={
            "finding_key": f"focus_drift:{focus_project}",
            "entity_id": focus_project,
            "finding_type": FINDING_FOCUS_DRIFT,
            "declared_state": f"Фокус недели: «{title[:140]}» ({focus_project})",
            "observed_state": (
                f"За 7 дней активность по фокусу {round(focus_share * 100)}%, "
                f"а {round(top_share * 100)}% — в {top_project} "
                f"({total} событий)"
            ),
            "summary": f"Команда не на фокусе: активность ушла в {top_project}",
            "severity": "medium",
            "confidence": score,
            "confidence_factors": factors,
            "evidence_refs": [
                {
                    "kind": "activity_distribution",
                    "window_days": 7,
                    "per_project": per_project,
                    "total": total,
                }
            ],
            "source_refs": [{"kind": "declaration", "key": KEY_FOCUS}],
        },
    )
    if outcome_emitted_finding(outcome):
        counts["findings"] += 1
    elif outcome == "proposed":
        counts["proposals"] += 1
    return counts
