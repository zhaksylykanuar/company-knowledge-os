"""Product system read model: problem -> hypothesis -> evidence -> result.

Active product areas are the real projects. Hypotheses come from the
founder's declaration; each is checked against stored reality:
supporting evidence (knowledge chunks that mention it), contradicting
evidence (stored risks), the validation_gap / evidence_contradiction
findings the hypothesis agent raised, and a next validation action.

No invented roadmap dates — the roadmap is the Now/Next/Later the
founder maintains in the UI, not a fabricated 30/60/90 calendar.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_models import DocumentChunk
from app.db.task_models import ExtractedRisk
from app.services.declarations import KEY_HYPOTHESES, get_declaration
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.knowledge_graph import slugify
from app.services.second_opinion import _finding_read_model

_WORD_RE = re.compile(r"[\w-]{4,}", re.UNICODE)
_STOP = {"что", "это", "если", "когда", "будет", "может", "нужно", "this", "that", "with"}


def _tokens(text: str) -> list[str]:
    seen: list[str] = []
    for tok in _WORD_RE.findall(str(text).casefold()):
        if tok in _STOP or tok in seen:
            continue
        seen.append(tok)
    return seen[:5]


def _like(column: Any, token: str) -> Any:
    # Escape LIKE wildcards so a token's underscore is a literal, not "_".
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


async def build_product_view(session: AsyncSession) -> dict[str, Any]:
    projects = list(
        (
            await session.execute(
                select(EntityRecord)
                .where(EntityRecord.entity_type == ENTITY_TYPE_PROJECT)
                .order_by(EntityRecord.canonical_name)
            )
        ).scalars()
    )
    active_areas = [
        {"entity_id": p.entity_id, "name": p.canonical_name} for p in projects
    ]

    # Product findings.
    finding_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == "open")
            .where(
                SecondOpinionFinding.finding_type.in_(
                    ["validation_gap", "evidence_contradiction"]
                )
            )
        )
    ).scalars()
    findings_by_hyp: dict[str, list[dict[str, Any]]] = {}
    product_findings: list[dict[str, Any]] = []
    for row in finding_rows:
        model = _finding_read_model(row)
        product_findings.append(model)
        if row.entity_id:
            findings_by_hyp.setdefault(row.entity_id, []).append(model)

    declaration = await get_declaration(session, key=KEY_HYPOTHESES)
    items = ((declaration or {}).get("payload") or {}).get("items") or []

    hypotheses: list[dict[str, Any]] = []
    for item in items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        declared_status = str(item.get("status") or "testing")
        tokens = _tokens(text)
        hyp_id = f"hypothesis:{slugify(text)[:80]}"

        supporting = 0
        contradicting: list[dict[str, Any]] = []
        if tokens:
            supporting = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(DocumentChunk)
                        .where(or_(*[_like(DocumentChunk.text, t) for t in tokens[:4]]))
                    )
                ).scalar()
                or 0
            )
            risk_rows = (
                await session.execute(
                    select(ExtractedRisk)
                    .where(or_(*[_like(ExtractedRisk.title, t) for t in tokens[:4]]))
                    .limit(5)
                )
            ).scalars()
            contradicting = [
                {"risk_id": r.id, "title": r.title[:160]} for r in risk_rows
            ]

        hyp_findings = findings_by_hyp.get(hyp_id, [])
        next_action = (
            hyp_findings[0].get("suggested_action")
            if hyp_findings
            else "Запланировать проверку гипотезы"
        )
        hypotheses.append(
            {
                "text": text,
                "declared_status": declared_status,
                "supporting_evidence_count": supporting,
                "contradicting_evidence": contradicting,
                "findings": hyp_findings,
                "next_validation_action": next_action,
                # Validated but unsupported is the flagged state.
                "flagged": declared_status == "validated"
                and (supporting == 0 or bool(contradicting)),
            }
        )

    return {
        "active_areas": active_areas,
        "hypotheses": hypotheses,
        "product_findings": product_findings,
        "counts": {
            "areas": len(active_areas),
            "hypotheses": len(hypotheses),
            "flagged_hypotheses": sum(1 for h in hypotheses if h["flagged"]),
            "product_findings": len(product_findings),
        },
    }
