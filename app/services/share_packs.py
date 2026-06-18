"""Share packs: prepare, review, approve and export evidence-backed updates.

A share pack is a reviewable artifact for a specific audience. AI generates
the draft; only a human can approve, export or revoke it. The pack freezes
a ``source_snapshot`` and a ``content_hash`` at generation, so what gets
exported is exactly what was reviewed. Any edit recomputes the hash and
resets approval, so a changed draft can never be exported under an old
approval (stale-hash protection). Investor/team exports are blocked if the
redaction manifest fails (e.g. raw source refs present, or finance leaked).

State machine: draft -> pending_approval -> approved -> exported, with
revoke reachable from any non-revoked state and reject sending an
approved/pending pack back to draft. Every transition writes one audit row.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.share_pack_models import SharePack
from app.services.curated_updates import (
    _founder_sections,
    _investor_sections,
    _section,
    _team_sections,
)
from app.services.inbox_audit import (
    ACTION_PACK_APPROVED,
    ACTION_PACK_EXPORTED,
    ACTION_PACK_FINDING_TOGGLED,
    ACTION_PACK_GENERATED,
    ACTION_PACK_NOTE_ADDED,
    ACTION_PACK_REGENERATED,
    ACTION_PACK_REJECTED,
    ACTION_PACK_REVOKED,
    ACTION_PACK_SECTION_EDITED,
    ACTION_PACK_SECTION_TOGGLED,
    record_inbox_action,
)
from app.services.operating_rhythm import build_decision_review
from app.services.role_views import build_investor_view
from app.services.second_opinion import STATUS_OPEN, list_findings
from app.services.visibility import (
    SCOPE_FOUNDER,
    SCOPE_INVESTOR,
    SCOPE_TEAM,
    redaction_manifest,
)

# --- pack catalogue -----------------------------------------------------

PACK_FOUNDER_WEEKLY_REVIEW = "founder_weekly_review"
PACK_TEAM_WEEKLY_BRIEF = "team_weekly_brief"
PACK_INVESTOR_UPDATE = "investor_update"
PACK_DECISION_SUMMARY = "decision_summary"
PACK_PRODUCT_PROGRESS_UPDATE = "product_progress_update"
PACK_RISK_REVIEW = "risk_review"

PACK_TYPES = frozenset(
    {
        PACK_FOUNDER_WEEKLY_REVIEW,
        PACK_TEAM_WEEKLY_BRIEF,
        PACK_INVESTOR_UPDATE,
        PACK_DECISION_SUMMARY,
        PACK_PRODUCT_PROGRESS_UPDATE,
        PACK_RISK_REVIEW,
    }
)

# Audience is fixed per pack type — redaction is never left ambiguous.
_PACK_AUDIENCE = {
    PACK_FOUNDER_WEEKLY_REVIEW: SCOPE_FOUNDER,
    PACK_TEAM_WEEKLY_BRIEF: SCOPE_TEAM,
    PACK_INVESTOR_UPDATE: SCOPE_INVESTOR,
    PACK_DECISION_SUMMARY: SCOPE_FOUNDER,
    PACK_PRODUCT_PROGRESS_UPDATE: SCOPE_INVESTOR,
    PACK_RISK_REVIEW: SCOPE_FOUNDER,
}

_PACK_TITLES = {
    PACK_FOUNDER_WEEKLY_REVIEW: "Founder weekly review",
    PACK_TEAM_WEEKLY_BRIEF: "Team weekly brief",
    PACK_INVESTOR_UPDATE: "Investor update",
    PACK_DECISION_SUMMARY: "Decision summary",
    PACK_PRODUCT_PROGRESS_UPDATE: "Product progress update",
    PACK_RISK_REVIEW: "Risk review",
}

_AUDIENCE_EXCLUDED = {
    SCOPE_FOUNDER: [],
    SCOPE_TEAM: [
        "investor_notes",
        "founder_private_conclusions",
        "raw_source_refs",
        "performance_ranking",
        "finance",
    ],
    SCOPE_INVESTOR: [
        "finance",
        "raw_evidence_refs",
        "internal_notes",
        "graph_hygiene",
        "personal_stamina",
        "founder_private_conclusions",
    ],
}

# Forbidden financial-HEALTH metrics. Deliberately excludes the declared
# fundraise ask (amount / "$" / "raise"), which IS allowed in an investor
# pack — only operating financials (MRR, runway, revenue, burn, …) leak.
_FINANCE_TERMS = (
    "mrr",
    "arr",
    "runway",
    "revenue",
    "burn rate",
    "ebitda",
    "p&l",
    "cash flow",
    "gross margin",
    "net margin",
    "выручк",
    "доход",
    "прибыл",
)
_STAMINA_TERMS = (
    "burned out",
    "burnout",
    "выгор",
    "перегруз",
    "overloaded",
    "stamina",
)
_INTERNAL_TERMS = (
    "internal note",
    "private note",
    "founder only",
    "founder-only",
    "for founder",
    "внутренняя заметка",
    "приватная заметка",
    "только для основателя",
)
_HYGIENE_TERMS = (
    "graph gardener",
    "gardener",
    "graph hygiene",
    "гигиена графа",
    "orphan node",
    "merge proposal",
)
# Which forbidden-content categories apply to which audience. Founder has
# no content restrictions. Team sees operational load, so stamina is NOT
# forbidden for team; investor is the most restricted.
_LEAK_CATEGORIES: dict[str, tuple[str, ...]] = {
    "finance_leak": _FINANCE_TERMS,
    "stamina_leak": _STAMINA_TERMS,
    "internal_note_leak": _INTERNAL_TERMS,
    "hygiene_leak": _HYGIENE_TERMS,
}
_CATEGORY_AUDIENCES: dict[str, set[str]] = {
    "finance_leak": {SCOPE_TEAM, SCOPE_INVESTOR},
    "stamina_leak": {SCOPE_INVESTOR},
    "internal_note_leak": {SCOPE_TEAM, SCOPE_INVESTOR},
    "hygiene_leak": {SCOPE_INVESTOR},
}

STATUS_DRAFT = "draft"
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_EXPORTED = "exported"
STATUS_REVOKED = "revoked"

_RISK_CATEGORY_LABELS = {
    "delivery_risk": "Риски сроков поставки",
    "execution_mismatch": "Расхождения план/факт",
    "focus_drift": "Дрейф фокуса",
    "validation_gap": "Непроверенные гипотезы",
    "evidence_contradiction": "Противоречия в данных",
    "stale_claim": "Устаревшие утверждения",
    "ownership_gap": "Пробелы в ответственности",
    "communication_silence": "Тишина в коммуникации",
}
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


# --- content builders (audience-redacted by construction) ---------------


async def _product_progress_sections(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    view = await build_investor_view(session, now=now)
    rl = SCOPE_INVESTOR
    progress = view["product_progress"]
    areas = progress.get("areas", [])
    observed_areas = sum(1 for a in areas if a.get("basis") == "observed")
    traction = view["traction"]
    observed_tr = [t for t in traction if t["basis"] == "observed"]
    return [
        _section(
            key="product_progress",
            title="Прогресс продукта",
            text=(
                f"Закрыто {progress.get('overall_progress_pct')}% задач; "
                f"областей: {len(areas)}"
                if progress.get("overall_progress_pct") is not None
                else "Прогресс собирается — данных пока недостаточно"
            ),
            observed=observed_areas,
            total=len(areas),
            redaction_level=rl,
        ),
        _section(
            key="traction",
            title="Traction (без финансов)",
            text="; ".join(f"{t['label']}: {t['value']}" for t in observed_tr)
            or "Сигналы traction собираются",
            observed=len(observed_tr),
            total=len(traction),
            redaction_level=rl,
        ),
        _section(
            key="what_changed",
            title="Что изменилось",
            text="; ".join(
                f"{c['label']}: {'+' if c['delta'] > 0 else ''}{c['delta']:g}"
                for c in view["what_changed"]
            )
            or "Существенных изменений за период не зафиксировано",
            observed=len(view["what_changed"]),
            total=max(len(view["what_changed"]), 1) if view["what_changed"] else 0,
            redaction_level=rl,
        ),
    ]


async def _decision_summary_sections(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    review = await build_decision_review(session, now=now)
    rl = SCOPE_FOUNDER
    counts = review["counts"]
    recent = review["recent_decisions"]
    consequences = review["consequences"]
    return [
        _section(
            key="pending",
            title="Ожидают решения",
            text=(
                f"Предложения: {counts.get('pending_proposals', 0)} · "
                f"спорные связи: {counts.get('pending_disputed_links', 0)}"
            ),
            observed=1,
            total=1,
            redaction_level=rl,
        ),
        _section(
            key="recent_decisions",
            title="Недавние решения",
            text="; ".join(
                f"{(d.get('next_state') or {}).get('status', d.get('action'))}: "
                f"{d.get('target_id')}"
                for d in recent[:6]
            )
            or "Решений за период не было",
            observed=len(recent),
            total=max(len(recent), 1) if recent else 0,
            redaction_level=rl,
        ),
        _section(
            key="consequences",
            title="Последствия",
            text="; ".join(
                f"{c.get('target_id')} → {c.get('decision')}"
                for c in consequences[:6]
            )
            or "Без зафиксированных последствий",
            observed=len(consequences),
            total=max(len(consequences), 1) if consequences else 0,
            redaction_level=rl,
        ),
    ]


async def _risk_review_sections(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    findings = await list_findings(session, status=STATUS_OPEN, limit=200)
    rl = SCOPE_FOUNDER
    by_cat: dict[str, dict[str, Any]] = {}
    for f in findings:
        label = _RISK_CATEGORY_LABELS.get(f.get("finding_type"))
        if not label:
            continue
        bucket = by_cat.setdefault(
            f["finding_type"], {"label": label, "count": 0, "severity": "low"}
        )
        bucket["count"] += 1
        if _SEVERITY_RANK.get(f.get("severity"), 3) < _SEVERITY_RANK.get(
            bucket["severity"], 3
        ):
            bucket["severity"] = f.get("severity")
    cats = sorted(
        by_cat.values(),
        key=lambda r: (_SEVERITY_RANK.get(r["severity"], 3), -r["count"]),
    )
    high = sorted(
        [f for f in findings if f.get("severity") == "high"],
        key=lambda f: f.get("finding_key") or "",
    )
    return [
        _section(
            key="by_category",
            title="Риски по категориям",
            text="; ".join(f"{c['label']} ({c['count']}, {c['severity']})" for c in cats)
            or "Существенных рисков не выявлено",
            observed=len(cats),
            total=max(len(cats), 1) if cats else 0,
            redaction_level=rl,
        ),
        _section(
            key="high_severity",
            title="Высокая severity",
            # Founder review may show raw summaries (audience is founder).
            text="; ".join(f["summary"] for f in high[:8])
            or "Высоких рисков нет",
            observed=len(high),
            total=max(len(high), 1) if high else 0,
            redaction_level=rl,
        ),
    ]


_SECTION_BUILDERS = {
    PACK_FOUNDER_WEEKLY_REVIEW: _founder_sections,
    PACK_TEAM_WEEKLY_BRIEF: _team_sections,
    PACK_INVESTOR_UPDATE: _investor_sections,
    PACK_PRODUCT_PROGRESS_UPDATE: _product_progress_sections,
    PACK_DECISION_SUMMARY: _decision_summary_sections,
    PACK_RISK_REVIEW: _risk_review_sections,
}


# --- ids + snapshot + hash ----------------------------------------------


async def _collect_ids(
    session: AsyncSession, *, audience: str
) -> tuple[list[str], list[str], list[str]]:
    """Finding / entity / source-event ids referenced by a pack.

    Raw source-event refs are populated ONLY for the founder audience; team
    and investor packs always get an empty source-ref list by contract.
    """

    findings = await list_findings(session, status=STATUS_OPEN, limit=200)
    if audience == SCOPE_TEAM:
        findings = [f for f in findings if f.get("visibility_scope") == SCOPE_TEAM]
    elif audience == SCOPE_INVESTOR:
        findings = [
            f for f in findings if f.get("visibility_scope") == SCOPE_INVESTOR
        ]
    finding_ids = sorted({f["finding_key"] for f in findings})
    entity_ids = sorted({f["entity_id"] for f in findings if f.get("entity_id")})
    source_event_ids: list[str] = []
    if audience == SCOPE_FOUNDER:
        seen: set[str] = set()
        for f in findings:
            for ref in f.get("evidence_refs") or []:
                if isinstance(ref, dict):
                    sid = ref.get("source_id") or ref.get("issue_key")
                    if isinstance(sid, str) and sid:
                        seen.add(sid)
        source_event_ids = sorted(seen)
    return finding_ids, entity_ids, source_event_ids


def _aggregate(sections: list[dict[str, Any]]) -> dict[str, Any]:
    included = [s for s in sections if s.get("included")]
    observed = sum(int(s.get("evidence_observed") or 0) for s in included)
    total = sum(int(s.get("evidence_total") or 0) for s in included)
    basis_counts = {"observed": 0, "declared": 0, "mixed": 0}
    for s in included:
        basis_counts[s.get("basis", "declared")] = (
            basis_counts.get(s.get("basis", "declared"), 0) + 1
        )
    return {
        "evidence_coverage": f"{observed}/{total} observed",
        "confidence": round(observed / total, 2) if total else 0.0,
        "declared_vs_observed": basis_counts,
    }


def _content_hash(
    *,
    pack_type: str,
    audience: str,
    title: str,
    summary: str,
    sections: list[dict[str, Any]],
    included_ids: list[str],
) -> str:
    included = [s for s in sections if s.get("included")]
    payload = "\n".join(
        [pack_type, audience, title, summary]
        + [f"{s['key']}::{s['text']}" for s in included]
        + sorted(str(i) for i in included_ids)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summary(pack_type: str, sections: list[dict[str, Any]]) -> str:
    first = next((s for s in sections if s.get("included")), None)
    head = _PACK_TITLES.get(pack_type, pack_type)
    return f"{head}: {first['text']}" if first else head


def _all_included_ids(row: SharePack) -> list[str]:
    return (
        list(row.included_finding_ids or [])
        + list(row.included_entity_ids or [])
        + list(row.included_source_event_ids or [])
    )


def _recompute_hash(row: SharePack) -> None:
    row.content_hash = _content_hash(
        pack_type=row.pack_type,
        audience=row.audience,
        title=row.title,
        summary=row.generated_summary,
        sections=list(row.sections or []),
        included_ids=_all_included_ids(row),
    )
    agg = _aggregate(list(row.sections or []))
    row.evidence_coverage = agg["evidence_coverage"]
    row.confidence = agg["confidence"]
    row.declared_vs_observed = agg["declared_vs_observed"]


def _reset_approval(row: SharePack) -> None:
    row.status = STATUS_DRAFT
    row.approved_by = None
    row.approved_at = None
    row.approved_content_hash = None


def _section_diff(row: SharePack) -> dict[str, Any] | None:
    """Diff the current included sections against the last approved snapshot."""

    approved = (row.approved_snapshot or {}).get("sections")
    if approved is None:
        return None
    approved_map = {s["key"]: s["text"] for s in approved}
    current = {
        s["key"]: s["text"] for s in (row.sections or []) if s.get("included")
    }
    changed = sorted(
        k for k in current if k in approved_map and current[k] != approved_map[k]
    )
    added = sorted(k for k in current if k not in approved_map)
    removed = sorted(k for k in approved_map if k not in current)
    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "has_diff": bool(changed or added or removed),
    }


def _pack_read_model(row: SharePack) -> dict[str, Any]:
    content_fresh = row.content_hash == (row.approved_content_hash or "")
    diff = _section_diff(row)
    is_exportable = (
        row.status == STATUS_APPROVED
        and content_fresh
        and not _critical_warnings(row)
    )
    return {
        "pack_id": row.pack_id,
        "company_id": row.company_id,
        "pack_type": row.pack_type,
        "audience": row.audience,
        "status": row.status,
        "title": row.title,
        "generated_summary": row.generated_summary,
        "sections": list(row.sections or []),
        "evidence_coverage": row.evidence_coverage,
        "confidence": row.confidence,
        "declared_vs_observed": row.declared_vs_observed,
        "redaction_manifest": row.redaction_manifest,
        "included_entity_ids": list(row.included_entity_ids or []),
        "included_finding_ids": list(row.included_finding_ids or []),
        "included_source_event_ids": list(row.included_source_event_ids or []),
        "created_by": row.created_by,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "exported_at": row.exported_at.isoformat() if row.exported_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "content_hash": row.content_hash,
        "approved_content_hash": row.approved_content_hash,
        "content_changed_since_approval": bool(diff and diff["has_diff"]),
        "section_diff": diff,
        "warnings": _leak_warnings(row),
        "is_exportable": is_exportable,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# --- leak warnings ------------------------------------------------------


def _leak_warnings(row: SharePack) -> list[dict[str, str]]:
    """Redaction-manifest checks. Critical warnings block export."""

    warnings: list[dict[str, str]] = []
    audience = row.audience
    if audience == SCOPE_FOUNDER:
        return warnings  # founder export has no content restrictions
    if row.included_source_event_ids:
        warnings.append(
            {
                "severity": "critical",
                "code": "raw_source_refs",
                "message": "Pack для не-founder содержит raw source refs",
            }
        )
    manifest = row.redaction_manifest or {}
    if manifest.get("raw_refs_visible") or manifest.get("finance_visible"):
        warnings.append(
            {
                "severity": "critical",
                "code": "manifest_inconsistent",
                "message": "Redaction manifest не запрещает raw/finance",
            }
        )
    # Scan the included (shareable) text against every forbidden-content
    # category for this audience — so manually edited / pasted text cannot
    # smuggle finance, internal notes, stamina or graph-hygiene past export.
    included_text = " ".join(
        str(s.get("text") or "")
        for s in (row.sections or [])
        if s.get("included")
    ).lower()
    for code, terms in _LEAK_CATEGORIES.items():
        if audience not in _CATEGORY_AUDIENCES[code]:
            continue
        hit = next((t for t in terms if t in included_text), None)
        if hit:
            warnings.append(
                {
                    "severity": "critical",
                    "code": code,
                    "message": f"{audience} pack содержит запрещённый контент: {hit}",
                }
            )
    return warnings


def _critical_warnings(row: SharePack) -> list[dict[str, str]]:
    return [w for w in _leak_warnings(row) if w["severity"] == "critical"]


# --- queries ------------------------------------------------------------


async def get_pack(session: AsyncSession, *, pack_id: str) -> SharePack | None:
    return await session.scalar(
        select(SharePack).where(SharePack.pack_id == pack_id)
    )


async def read_pack(
    session: AsyncSession, *, pack_id: str
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    return _pack_read_model(row) if row else None


async def list_packs(
    session: AsyncSession,
    *,
    audience: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = select(SharePack).order_by(SharePack.created_at.desc()).limit(limit)
    if audience is not None:
        query = query.where(SharePack.audience == audience)
    if status is not None:
        query = query.where(SharePack.status == status)
    rows = (await session.execute(query)).scalars()
    return [_pack_read_model(row) for row in rows]


# --- generate -----------------------------------------------------------


async def _build_content(
    session: AsyncSession, *, pack_type: str, audience: str, now: datetime
) -> dict[str, Any]:
    sections = await _SECTION_BUILDERS[pack_type](session, now=now)
    finding_ids, entity_ids, source_event_ids = await _collect_ids(
        session, audience=audience
    )
    title = _PACK_TITLES[pack_type]
    summary = _summary(pack_type, sections)
    included_ids = finding_ids + entity_ids + source_event_ids
    content_hash = _content_hash(
        pack_type=pack_type,
        audience=audience,
        title=title,
        summary=summary,
        sections=sections,
        included_ids=included_ids,
    )
    agg = _aggregate(sections)
    included_sections = [s["key"] for s in sections if s.get("included")]
    manifest = redaction_manifest(
        audience,
        included_sections=included_sections,
        excluded_sections=_AUDIENCE_EXCLUDED[audience],
    )
    snapshot = {
        "frozen_at": now.isoformat(),
        "finding_count": len(finding_ids),
        "entity_count": len(entity_ids),
        "source_event_count": len(source_event_ids),
        "section_keys": [s["key"] for s in sections],
    }
    return {
        "sections": sections,
        "title": title,
        "summary": summary,
        "finding_ids": finding_ids,
        "entity_ids": entity_ids,
        "source_event_ids": source_event_ids,
        "content_hash": content_hash,
        "manifest": manifest,
        "snapshot": snapshot,
        **agg,
    }


async def generate_pack(
    session: AsyncSession,
    *,
    pack_type: str,
    created_by: str = "founder",
    company_id: str = "default",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate a draft pack. Idempotent: identical content (same hash) for
    the same pack type returns the existing non-revoked pack."""

    if pack_type not in PACK_TYPES:
        raise ValueError(f"unknown pack_type: {pack_type}")
    safe_now = now or datetime.now(timezone.utc)
    audience = _PACK_AUDIENCE[pack_type]
    content = await _build_content(
        session, pack_type=pack_type, audience=audience, now=safe_now
    )

    existing = await session.scalar(
        select(SharePack)
        .where(SharePack.pack_type == pack_type)
        .where(SharePack.content_hash == content["content_hash"])
        .where(SharePack.status != STATUS_REVOKED)
        .order_by(SharePack.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return {**_pack_read_model(existing), "idempotent": True}

    pack_id = f"pack:{pack_type}:{uuid4().hex[:12]}"
    row = SharePack(
        pack_id=pack_id,
        company_id=company_id,
        pack_type=pack_type,
        audience=audience,
        status=STATUS_DRAFT,
        title=content["title"],
        generated_summary=content["summary"],
        sections=content["sections"],
        evidence_coverage=content["evidence_coverage"],
        confidence=content["confidence"],
        declared_vs_observed=content["declared_vs_observed"],
        redaction_manifest=content["manifest"],
        included_finding_ids=content["finding_ids"],
        included_entity_ids=content["entity_ids"],
        included_source_event_ids=content["source_event_ids"],
        created_by=created_by,
        content_hash=content["content_hash"],
        source_snapshot=content["snapshot"],
    )
    session.add(row)
    await session.flush()
    await record_inbox_action(
        session,
        action=ACTION_PACK_GENERATED,
        actor=created_by,
        target_id=pack_id,
        previous_state=None,
        next_state={"status": STATUS_DRAFT, "pack_type": pack_type},
        reversible=True,
        details={"audience": audience, "content_hash": content["content_hash"]},
    )
    return {**_pack_read_model(row), "idempotent": False}


# --- editing (each resets approval + recomputes hash) -------------------


async def regenerate_pack(
    session: AsyncSession,
    *,
    pack_id: str,
    reviewer_id: str = "founder",
    now: datetime | None = None,
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    if row.status in {STATUS_EXPORTED, STATUS_REVOKED}:
        raise ValueError(f"cannot regenerate a {row.status} pack")
    safe_now = now or datetime.now(timezone.utc)
    content = await _build_content(
        session, pack_type=row.pack_type, audience=row.audience, now=safe_now
    )
    row.sections = content["sections"]
    row.generated_summary = content["summary"]
    row.included_finding_ids = content["finding_ids"]
    row.included_entity_ids = content["entity_ids"]
    row.included_source_event_ids = content["source_event_ids"]
    row.redaction_manifest = content["manifest"]
    row.source_snapshot = content["snapshot"]
    _reset_approval(row)
    _recompute_hash(row)
    await session.flush()
    await record_inbox_action(
        session,
        action=ACTION_PACK_REGENERATED,
        actor=reviewer_id,
        target_id=pack_id,
        previous_state={"status": row.status},
        next_state={"status": STATUS_DRAFT, "content_hash": row.content_hash},
        reversible=True,
    )
    return _pack_read_model(row)


async def _mutate(
    session: AsyncSession,
    *,
    pack_id: str,
    action: str,
    reviewer_id: str,
    apply,
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    if row.status in {STATUS_EXPORTED, STATUS_REVOKED}:
        raise ValueError(f"cannot edit a {row.status} pack")
    previous_status = row.status
    apply(row)
    _reset_approval(row)
    _recompute_hash(row)
    await session.flush()
    await record_inbox_action(
        session,
        action=action,
        actor=reviewer_id,
        target_id=pack_id,
        previous_state={"status": previous_status},
        next_state={"status": STATUS_DRAFT, "content_hash": row.content_hash},
        reversible=True,
        details=details,
    )
    return _pack_read_model(row)


async def edit_section(
    session: AsyncSession,
    *,
    pack_id: str,
    section_key: str,
    text: str,
    reviewer_id: str = "founder",
) -> dict[str, Any] | None:
    def _apply(row: SharePack) -> None:
        # Rebuild with fresh dicts so SQLAlchemy flushes the JSON change
        # (in-place mutation of a nested dict is not tracked).
        row.sections = [
            {**s, "text": text[:2000], "edited": True}
            if s.get("key") == section_key
            else dict(s)
            for s in (row.sections or [])
        ]

    return await _mutate(
        session,
        pack_id=pack_id,
        action=ACTION_PACK_SECTION_EDITED,
        reviewer_id=reviewer_id,
        apply=_apply,
        details={"section_key": section_key},
    )


async def set_section_included(
    session: AsyncSession,
    *,
    pack_id: str,
    section_key: str,
    included: bool,
    reviewer_id: str = "founder",
) -> dict[str, Any] | None:
    def _apply(row: SharePack) -> None:
        row.sections = [
            {**s, "included": included} if s.get("key") == section_key else dict(s)
            for s in (row.sections or [])
        ]

    return await _mutate(
        session,
        pack_id=pack_id,
        action=ACTION_PACK_SECTION_TOGGLED,
        reviewer_id=reviewer_id,
        apply=_apply,
        details={"section_key": section_key, "included": included},
    )


async def set_finding_included(
    session: AsyncSession,
    *,
    pack_id: str,
    finding_id: str,
    included: bool,
    reviewer_id: str = "founder",
) -> dict[str, Any] | None:
    def _apply(row: SharePack) -> None:
        ids = list(row.included_finding_ids or [])
        if included and finding_id not in ids:
            ids.append(finding_id)
        elif not included and finding_id in ids:
            ids.remove(finding_id)
        row.included_finding_ids = sorted(ids)

    return await _mutate(
        session,
        pack_id=pack_id,
        action=ACTION_PACK_FINDING_TOGGLED,
        reviewer_id=reviewer_id,
        apply=_apply,
        details={"finding_id": finding_id, "included": included},
    )


async def add_public_note(
    session: AsyncSession,
    *,
    pack_id: str,
    note: str,
    reviewer_id: str = "founder",
) -> dict[str, Any] | None:
    def _apply(row: SharePack) -> None:
        sections = [dict(s) for s in (row.sections or [])]
        note_count = len(
            [s for s in sections if str(s.get("key", "")).startswith("public_note")]
        )
        sections.append(
            _section(
                key=f"public_note_{note_count}",
                title="Публичная заметка",
                text=note[:2000],
                observed=0,
                total=0,
                redaction_level=row.audience,
            )
        )
        row.sections = sections

    return await _mutate(
        session,
        pack_id=pack_id,
        action=ACTION_PACK_NOTE_ADDED,
        reviewer_id=reviewer_id,
        apply=_apply,
    )


# --- approve / reject / export / revoke ---------------------------------


async def approve_pack(
    session: AsyncSession,
    *,
    pack_id: str,
    content_hash: str,
    reviewer_id: str = "founder",
    now: datetime | None = None,
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    if row.status not in {STATUS_DRAFT, STATUS_PENDING, STATUS_APPROVED}:
        raise ValueError(f"cannot approve a {row.status} pack")
    if content_hash != row.content_hash:
        raise ValueError("content has changed since review — re-review and approve")
    # Idempotent: already approved at this exact content.
    if row.status == STATUS_APPROVED and row.approved_content_hash == content_hash:
        return {**_pack_read_model(row), "idempotent": True}
    safe_now = now or datetime.now(timezone.utc)
    previous_status = row.status
    row.status = STATUS_APPROVED
    row.approved_by = reviewer_id
    row.approved_at = safe_now
    row.approved_content_hash = content_hash
    # Freeze the approved content so the UI can diff future drafts against it.
    row.approved_snapshot = {
        "content_hash": content_hash,
        "approved_at": safe_now.isoformat(),
        "sections": [
            {"key": s["key"], "title": s["title"], "text": s["text"]}
            for s in (row.sections or [])
            if s.get("included")
        ],
    }
    await session.flush()
    await record_inbox_action(
        session,
        action=ACTION_PACK_APPROVED,
        actor=reviewer_id,
        target_id=pack_id,
        previous_state={"status": previous_status},
        next_state={"status": STATUS_APPROVED, "content_hash": content_hash},
        reversible=True,
    )
    return {**_pack_read_model(row), "idempotent": False}


async def reject_pack(
    session: AsyncSession,
    *,
    pack_id: str,
    reviewer_id: str = "founder",
    reason: str | None = None,
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    if row.status in {STATUS_EXPORTED, STATUS_REVOKED}:
        raise ValueError(f"cannot reject a {row.status} pack")
    previous_status = row.status
    _reset_approval(row)
    await session.flush()
    await record_inbox_action(
        session,
        action=ACTION_PACK_REJECTED,
        actor=reviewer_id,
        target_id=pack_id,
        previous_state={"status": previous_status},
        next_state={"status": STATUS_DRAFT},
        reversible=True,
        details={"reason": reason},
    )
    return _pack_read_model(row)


async def export_pack(
    session: AsyncSession,
    *,
    pack_id: str,
    reviewer_id: str = "founder",
    now: datetime | None = None,
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    if row.status == STATUS_EXPORTED and row.content_hash == row.approved_content_hash:
        # Idempotent: already exported at this exact, approved content.
        return {
            **build_export_preview(row),
            "exported": True,
            "idempotent": True,
        }
    if row.status != STATUS_APPROVED:
        raise ValueError(f"cannot export a {row.status} pack (must be approved)")
    if row.content_hash != row.approved_content_hash:
        raise ValueError("draft changed after approval — re-approve before export")
    critical = _critical_warnings(row)
    if critical:
        raise ValueError(
            "redaction manifest failed: " + "; ".join(w["message"] for w in critical)
        )
    safe_now = now or datetime.now(timezone.utc)
    row.status = STATUS_EXPORTED
    row.exported_at = safe_now
    await session.flush()
    await record_inbox_action(
        session,
        action=ACTION_PACK_EXPORTED,
        actor=reviewer_id,
        target_id=pack_id,
        previous_state={"status": STATUS_APPROVED},
        next_state={"status": STATUS_EXPORTED, "content_hash": row.content_hash},
        reversible=True,
    )
    return {**build_export_preview(row), "exported": True, "idempotent": False}


async def revoke_pack(
    session: AsyncSession,
    *,
    pack_id: str,
    reviewer_id: str = "founder",
    reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    if row.status == STATUS_REVOKED:
        return {**_pack_read_model(row), "idempotent": True}
    safe_now = now or datetime.now(timezone.utc)
    previous_status = row.status
    row.status = STATUS_REVOKED
    row.revoked_at = safe_now
    await session.flush()
    await record_inbox_action(
        session,
        action=ACTION_PACK_REVOKED,
        actor=reviewer_id,
        target_id=pack_id,
        previous_state={"status": previous_status},
        next_state={"status": STATUS_REVOKED},
        reversible=False,
        details={"reason": reason},
    )
    return {**_pack_read_model(row), "idempotent": False}


# --- export preview -----------------------------------------------------

_CLAIM_STATUS = {
    "observed": "observed",
    "mixed": "observed",
    "declared": "declared",
}


def _claim_status(section: dict[str, Any]) -> str:
    basis = section.get("basis", "declared")
    if basis == "declared" and int(section.get("evidence_total") or 0) > 0:
        return "evidence_collecting"
    return _CLAIM_STATUS.get(basis, "declared")


def build_export_preview(row: SharePack) -> dict[str, Any]:
    """The audience-facing view: what will be shared / excluded, coverage,
    confidence, claims with status, redaction manifest and warnings."""

    sections = list(row.sections or [])
    included = [s for s in sections if s.get("included")]
    excluded = [s for s in sections if not s.get("included")]
    claims = [
        {
            "claim": s["text"],
            "section": s["key"],
            "status": _claim_status(s),
            "confidence": s.get("confidence"),
        }
        for s in included
    ]
    export_text = "\n\n".join(f"## {s['title']}\n{s['text']}" for s in included)
    return {
        "pack_id": row.pack_id,
        "pack_type": row.pack_type,
        "audience": row.audience,
        "status": row.status,
        "what_will_be_shared": [
            {"key": s["key"], "title": s["title"], "text": s["text"]}
            for s in included
        ],
        "what_is_excluded": [
            {"key": s["key"], "title": s["title"]} for s in excluded
        ],
        "evidence_coverage": row.evidence_coverage,
        "confidence": row.confidence,
        "claims": claims,
        "redaction_manifest": row.redaction_manifest,
        "warnings": _leak_warnings(row),
        "export_text": export_text,
    }


async def build_pack_preview(
    session: AsyncSession, *, pack_id: str
) -> dict[str, Any] | None:
    row = await get_pack(session, pack_id=pack_id)
    if row is None:
        return None
    return build_export_preview(row)


# --- notification helpers (reused by the notification center) -----------

STALE_APPROVED_DAYS = 7


async def packs_awaiting_approval(
    session: AsyncSession, *, limit: int = 50
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SharePack)
            .where(SharePack.status.in_([STATUS_DRAFT, STATUS_PENDING]))
            .order_by(SharePack.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [_pack_read_model(r) for r in rows]


async def stale_approved_packs(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    safe_now = now or datetime.now(timezone.utc)
    cutoff = safe_now - timedelta(days=STALE_APPROVED_DAYS)
    rows = (
        await session.execute(
            select(SharePack)
            .where(SharePack.status == STATUS_APPROVED)
            .where(SharePack.approved_at < cutoff)
            .order_by(SharePack.approved_at)
            .limit(limit)
        )
    ).scalars()
    return [_pack_read_model(r) for r in rows]


async def last_approved_pack(
    session: AsyncSession, *, audience: str
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(SharePack)
        .where(SharePack.audience == audience)
        .where(SharePack.status.in_([STATUS_APPROVED, STATUS_EXPORTED]))
        .order_by(SharePack.approved_at.desc())
        .limit(1)
    )
    return _pack_read_model(row) if row else None
