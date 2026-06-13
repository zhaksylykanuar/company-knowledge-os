"""Curated updates: evidence-backed summaries the founder approves before export.

Three kinds — founder weekly, team brief, investor update — each composed
deterministically from the role read models (never an LLM, never external
delivery). Every section reports its text summary, evidence coverage
(observed vs declared), a confidence derived from that coverage, its
redaction level and whether it is included. Nothing is "exported" until
the founder approves: ``approve_update`` records an audit row and only
then returns the final shareable text. Approval is idempotent on the
content hash — approving the same draft twice does not double-log.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbox_audit import (
    ACTION_UPDATE_APPROVED,
    list_inbox_actions,
    record_inbox_action,
)
from app.services.operating_rhythm import build_weekly_review
from app.services.role_views import build_investor_view, build_team_workspace
from app.services.visibility import (
    SCOPE_FOUNDER,
    SCOPE_INVESTOR,
    SCOPE_TEAM,
    redaction_manifest,
)

KIND_FOUNDER_WEEKLY = "founder_weekly"
KIND_TEAM_BRIEF = "team_brief"
KIND_INVESTOR_UPDATE = "investor_update"
UPDATE_KINDS = frozenset(
    {KIND_FOUNDER_WEEKLY, KIND_TEAM_BRIEF, KIND_INVESTOR_UPDATE}
)

_KIND_REDACTION = {
    KIND_FOUNDER_WEEKLY: SCOPE_FOUNDER,
    KIND_TEAM_BRIEF: SCOPE_TEAM,
    KIND_INVESTOR_UPDATE: SCOPE_INVESTOR,
}

_KIND_EXCLUDED = {
    KIND_FOUNDER_WEEKLY: [],
    KIND_TEAM_BRIEF: [
        "investor_notes",
        "founder_private_conclusions",
        "raw_source_refs",
        "performance_ranking",
    ],
    KIND_INVESTOR_UPDATE: [
        "finance",
        "raw_evidence_refs",
        "internal_notes",
        "people_detail",
        "graph_hygiene",
        "personal_stamina",
    ],
}


def _section(
    *,
    key: str,
    title: str,
    text: str,
    observed: int,
    total: int,
    redaction_level: str,
    included: bool = True,
) -> dict[str, Any]:
    if total <= 0:
        basis, confidence = "declared", 0.0
    elif observed >= total:
        basis, confidence = "observed", 1.0
    elif observed == 0:
        basis, confidence = "declared", 0.0
    else:
        basis, confidence = "mixed", round(observed / total, 2)
    return {
        "key": key,
        "title": title,
        "text": text,
        "evidence_coverage": f"{observed}/{total} observed",
        "evidence_observed": observed,
        "evidence_total": total,
        "confidence": confidence,
        "basis": basis,
        "declared_vs_observed": (
            "observed" if basis == "observed" else "declared, evidence collecting"
            if basis == "declared" else "mixed"
        ),
        "redaction_level": redaction_level,
        "included": included,
    }


# --------------------------------------------------------------------------
# per-kind section builders
# --------------------------------------------------------------------------


async def _investor_sections(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    view = await build_investor_view(session, now=now)
    snap = view["company_snapshot"]
    progress = view["product_progress"]
    traction = view["traction"]
    roadmap = view["roadmap"]
    risks = view["key_risks"]
    changed = view["what_changed"]
    ask = view.get("ask")
    rl = SCOPE_INVESTOR

    sections = []
    sections.append(
        _section(
            key="snapshot",
            title="Снимок компании",
            text=(snap.get("headline") or "—")
            + f" · состояние: {snap['health_headline']} · областей: {snap['active_areas']}",
            observed=1 if snap.get("health") != "unknown" else 0,
            total=1,
            redaction_level=rl,
        )
    )
    areas = progress.get("areas", [])
    observed_areas = sum(1 for a in areas if a.get("basis") == "observed")
    overall = progress.get("overall_progress_pct")
    sections.append(
        _section(
            key="product_progress",
            title="Прогресс продукта",
            text=(
                f"Закрыто {overall}% задач по продукту; областей: {len(areas)}"
                if overall is not None
                else "Прогресс собирается — данных пока недостаточно"
            ),
            observed=observed_areas,
            total=len(areas),
            redaction_level=rl,
        )
    )
    observed_tr = [t for t in traction if t["basis"] == "observed"]
    sections.append(
        _section(
            key="traction",
            title="Traction (без финансов)",
            text=(
                "; ".join(f"{t['label']}: {t['value']}" for t in observed_tr)
                or "Сигналы traction собираются (evidence collecting)"
            ),
            observed=len(observed_tr),
            total=len(traction),
            redaction_level=rl,
        )
    )
    roadmap_items = [i for h in roadmap for i in h["items"]]
    sections.append(
        _section(
            key="roadmap",
            title="Roadmap 30/60/90",
            text="; ".join(
                f"{h['horizon']}д: {', '.join(h['items'])}"
                for h in roadmap
                if h["items"]
            )
            or "Roadmap не задан",
            observed=0,
            total=len(roadmap_items),
            redaction_level=rl,
        )
    )
    sections.append(
        _section(
            key="key_risks",
            title="Ключевые риски",
            text="; ".join(f"{r['category']} ({r['count']})" for r in risks)
            or "Существенных рисков не выявлено",
            observed=len(risks),
            total=len(risks),
            redaction_level=rl,
        )
    )
    sections.append(
        _section(
            key="what_changed",
            title="Что изменилось",
            text="; ".join(
                f"{c['label']}: {'+' if c['delta'] > 0 else ''}{c['delta']:g}"
                for c in changed
            )
            or "Существенных изменений за период не зафиксировано",
            observed=len(changed),
            total=max(len(changed), 1) if changed else 0,
            redaction_level=rl,
        )
    )
    if ask:
        sections.append(
            _section(
                key="ask",
                title="Ask / следующий milestone",
                text=" · ".join(
                    p
                    for p in (
                        ask.get("ask"),
                        ask.get("milestone"),
                        ask.get("use_of_funds"),
                    )
                    if p
                ),
                observed=0,
                total=1,
                redaction_level=rl,
            )
        )
    return sections


async def _team_sections(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    workspace = await build_team_workspace(session, now=now)
    counts = workspace["counts"]
    main = workspace.get("main_quest") or {}
    rl = SCOPE_TEAM
    decisions = workspace.get("decisions_needed", [])
    gaps = workspace.get("ownership_gaps", [])

    return [
        _section(
            key="focus",
            title="Фокус недели",
            text=main.get("focus") or "Фокус недели не задан",
            observed=1 if main.get("focus") else 0,
            total=1,
            redaction_level=rl,
        ),
        _section(
            key="your_work",
            title="Что разблокировать / доделать",
            text=(
                f"Заблокировано: {counts['blocked']} · просрочено: {counts['overdue']} "
                f"· без владельца: {counts['ownerless']} · застряло: {counts['stale']}"
            ),
            observed=1,
            total=1,
            redaction_level=rl,
        ),
        _section(
            key="decisions_needed",
            title="Что прояснить / решить",
            text="; ".join(f["summary"] for f in decisions[:5])
            or "Открытых вопросов к команде нет",
            observed=len(decisions),
            total=max(len(decisions), 1) if decisions else 0,
            redaction_level=rl,
        ),
        _section(
            key="ownership_gaps",
            title="Пробелы в ответственности",
            text="; ".join(g["summary"] for g in gaps[:5])
            or "Пробелов в ответственности нет",
            observed=len(gaps),
            total=max(len(gaps), 1) if gaps else 0,
            redaction_level=rl,
        ),
    ]


async def _founder_sections(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    review = await build_weekly_review(session, now=now, viewer_scope=SCOPE_FOUNDER)
    rl = SCOPE_FOUNDER
    deltas = review["what_changed"]["metric_deltas"]
    stuck = review["stuck"]
    ai = review["ai_sees_differently"]
    decisions = review["decisions_needed"]["findings"]
    new_risks = review["new_risks"]
    closed = review["closed"]

    return [
        _section(
            key="what_changed",
            title="Что изменилось",
            text="; ".join(
                f"{d['label']}: {'+' if d['delta'] > 0 else ''}{d['delta']:g}"
                for d in deltas
            )
            + (
                f" · обработано новых сигналов: {review['what_changed']['new_evidence_processed']}"
            ),
            observed=len(deltas),
            total=max(len(deltas), 1),
            redaction_level=rl,
        ),
        _section(
            key="stuck",
            title="Что застряло",
            text=(
                f"Заблокировано: {stuck['blocked_count']} · застряло: {stuck['stale_count']} "
                f"· просрочено: {stuck['overdue_count']}"
            ),
            observed=1,
            total=1,
            redaction_level=rl,
        ),
        _section(
            key="ai_sees_differently",
            title="Где AI видит иначе",
            text="; ".join(f["summary"] for f in ai[:5])
            or "Конфликтов план/факт нет",
            observed=len(ai),
            total=max(len(ai), 1) if ai else 0,
            redaction_level=rl,
        ),
        _section(
            key="decisions_needed",
            title="Какие решения нужны",
            text="; ".join(f["summary"] for f in decisions[:5])
            or "Открытых решений нет",
            observed=len(decisions),
            total=max(len(decisions), 1) if decisions else 0,
            redaction_level=rl,
        ),
        _section(
            key="new_risks",
            title="Что стало риском",
            text="; ".join(f["summary"] for f in new_risks[:5])
            or "Новых высоких рисков нет",
            observed=len(new_risks),
            total=max(len(new_risks), 1) if new_risks else 0,
            redaction_level=rl,
        ),
        _section(
            key="closed",
            title="Что закрыто",
            text=f"Закрыто решений/действий за неделю: {closed['count']}",
            observed=1 if closed["count"] else 0,
            total=1,
            redaction_level=rl,
        ),
    ]


_KIND_BUILDERS = {
    KIND_FOUNDER_WEEKLY: _founder_sections,
    KIND_TEAM_BRIEF: _team_sections,
    KIND_INVESTOR_UPDATE: _investor_sections,
}


def _content_hash(kind: str, sections: list[dict[str, Any]]) -> str:
    payload = kind + "\n" + "\n".join(
        f"{s['key']}::{s['text']}" for s in sections if s["included"]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _export_text(kind: str, sections: list[dict[str, Any]]) -> str:
    lines = []
    for s in sections:
        if not s["included"]:
            continue
        tag = "" if s["basis"] == "observed" else f" [{s['declared_vs_observed']}]"
        lines.append(f"## {s['title']}{tag}\n{s['text']}")
    return "\n\n".join(lines)


async def build_update_draft(
    session: AsyncSession,
    *,
    kind: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if kind not in UPDATE_KINDS:
        raise ValueError(f"unknown update kind: {kind}")
    safe_now = now or datetime.now(timezone.utc)
    sections = await _KIND_BUILDERS[kind](session, now=safe_now)
    content_hash = _content_hash(kind, sections)
    included = [s["key"] for s in sections if s["included"]]
    observed_total = sum(s["evidence_observed"] for s in sections)
    evidence_total = sum(s["evidence_total"] for s in sections)
    return {
        "kind": kind,
        "redaction_level": _KIND_REDACTION[kind],
        "redaction_manifest": redaction_manifest(
            _KIND_REDACTION[kind],
            included_sections=included,
            excluded_sections=_KIND_EXCLUDED[kind],
        ),
        "generated_at": safe_now.isoformat(),
        "requires_approval": True,
        "approved": False,
        "sections": sections,
        "included_sections": included,
        "excluded_sections": _KIND_EXCLUDED[kind],
        "content_hash": content_hash,
        "evidence_coverage": (
            f"{observed_total}/{evidence_total} observed"
            if evidence_total
            else "0/0 observed"
        ),
        "preview_text": _export_text(kind, sections),
    }


async def approve_update(
    session: AsyncSession,
    *,
    kind: str,
    content_hash: str,
    reviewer_id: str = "founder",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record approval and return the final export text. Idempotent on hash."""

    if kind not in UPDATE_KINDS:
        raise ValueError(f"unknown update kind: {kind}")
    safe_now = now or datetime.now(timezone.utc)
    target_id = f"update:{kind}:{content_hash[:24]}"

    existing = await list_inbox_actions(session, target_id=target_id, limit=5)
    already = next(
        (a for a in existing if a.get("action") == ACTION_UPDATE_APPROVED), None
    )

    # Re-derive the current draft so the export text matches the hash.
    draft = await build_update_draft(session, kind=kind, now=safe_now)
    if draft["content_hash"] != content_hash:
        raise ValueError("content has changed since draft — review and re-approve")

    if already is None:
        await record_inbox_action(
            session,
            action=ACTION_UPDATE_APPROVED,
            actor=reviewer_id,
            target_id=target_id,
            previous_state={"approved": False},
            next_state={"approved": True, "kind": kind},
            reversible=True,
            details={
                "kind": kind,
                "content_hash": content_hash,
                "redaction_level": _KIND_REDACTION[kind],
            },
        )

    return {
        "kind": kind,
        "approved": True,
        "idempotent": already is not None,
        "approved_at": (already.get("created_at") if already else safe_now.isoformat()),
        "content_hash": content_hash,
        "redaction_level": _KIND_REDACTION[kind],
        "export_text": draft["preview_text"],
    }
