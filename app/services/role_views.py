"""Role-scoped read models: team workspace and investor view.

Visibility is enforced in the *backend*, not the frontend. These
builders compose the existing read models and then strip everything the
audience must not see, returning a document that is already safe to
render verbatim.

Team workspace — the working view: quests, operational load, product
work, ownership gaps and the decisions/blockers the team needs to act
on. It redacts every finding through ``redact_finding(view=team)`` so
founder-only conclusions, private notes and raw source refs never reach
it. There is no performance ranking and no productivity score.

Investor view — a curated executive summary: company snapshot, product
progress, traction (never finance), declared 30/60/90 roadmap, key
risks at the category level, what changed, evidence-backed claims, open
questions and the declared ask. It never emits raw evidence/source
refs, internal notes, people/stamina detail, graph-hygiene internals or
any money figure. Every claim is tagged ``observed`` (real data, with
its data-availability state) or ``declared`` (stated, evidence still
collecting).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.data_availability import (
    STATUS_READY,
    get_availability,
)
from app.services.declarations import (
    KEY_ASK,
    KEY_COMPANY,
    KEY_HYPOTHESES,
    KEY_ROADMAP,
    get_declaration,
)
from app.services.execution_view import build_execution_view
from app.services.founder_overview import build_founder_overview
from app.services.metric_collector import GLOBAL_SCOPE, metric_series
from app.services.product_view import build_product_view
from app.services.second_opinion import STATUS_OPEN, list_findings
from app.services.team_view import build_team_view
from app.services.visibility import (
    SCOPE_INVESTOR,
    SCOPE_TEAM,
    redact_finding,
    redaction_manifest,
)

_INVESTOR_SECTIONS = [
    "company_snapshot",
    "product_progress",
    "traction",
    "roadmap",
    "key_risks",
    "what_changed",
    "evidence_backed_claims",
    "open_questions",
    "ask",
]
_INVESTOR_EXCLUDED = [
    "finance",
    "raw_evidence_refs",
    "internal_notes",
    "graph_hygiene",
    "personal_stamina",
    "founder_private_conclusions",
]
_TEAM_SECTIONS = [
    "quests",
    "team_load",
    "decisions_needed",
    "ownership_gaps",
    "product_work",
]
_TEAM_EXCLUDED = [
    "investor_notes",
    "founder_private_conclusions",
    "raw_source_refs",
    "performance_ranking",
    "finance",
]

# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def _redact_findings(
    findings: list[dict[str, Any]], viewer_scope: str
) -> list[dict[str, Any]]:
    """Map a finding list through the audience redactor, dropping hidden ones."""

    out: list[dict[str, Any]] = []
    for finding in findings or []:
        redacted = redact_finding(finding, viewer_scope)
        if redacted is not None:
            out.append(redacted)
    return out


def _redact_quest(quest: dict[str, Any], viewer_scope: str) -> dict[str, Any]:
    """Strip founder-only findings from a quest and recount evidence."""

    safe = dict(quest)
    safe_findings = _redact_findings(quest.get("findings", []), viewer_scope)
    safe["findings"] = safe_findings
    safe["evidence_count"] = len(safe_findings)
    return safe


# --------------------------------------------------------------------------
# team workspace
# --------------------------------------------------------------------------


async def build_team_workspace(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The team's working view — what to do / clarify / unblock.

    No founder-only conclusions, no investor/private notes, no raw
    sensitive source refs, no performance ranking.
    """

    safe_now = now or datetime.now(timezone.utc)

    execution = await build_execution_view(session, now=safe_now)
    team = await build_team_view(session, now=safe_now)
    product = await build_product_view(session)

    # Quests are the team's own work; only their attached findings need
    # redaction so founder-only conclusions never leak into the board.
    def _quests(bucket: str) -> list[dict[str, Any]]:
        return [_redact_quest(q, SCOPE_TEAM) for q in execution.get(bucket, [])]

    # Decisions/clarifications the team needs: open, team-scoped findings.
    open_findings = await list_findings(session, status=STATUS_OPEN, limit=200)
    team_findings = _redact_findings(open_findings, SCOPE_TEAM)
    decisions_needed = [
        f
        for f in team_findings
        if f.get("finding_type")
        in {"execution_mismatch", "delivery_risk", "ownership_gap", "stale_claim"}
    ][:12]

    # Product work, team-safe: declared hypotheses + their team-scoped
    # findings, contradiction *counts* only (no raw risk titles).
    product_work = []
    for hyp in product.get("hypotheses", []):
        product_work.append(
            {
                "text": hyp["text"],
                "declared_status": hyp["declared_status"],
                "supporting_evidence_count": hyp["supporting_evidence_count"],
                "contradicting_evidence_count": len(
                    hyp.get("contradicting_evidence") or []
                ),
                "findings": _redact_findings(hyp.get("findings", []), SCOPE_TEAM),
                "next_validation_action": hyp.get("next_validation_action"),
            }
        )

    return {
        "role": SCOPE_TEAM,
        "generated_at": safe_now.isoformat(),
        "redaction_manifest": redaction_manifest(
            SCOPE_TEAM,
            included_sections=_TEAM_SECTIONS,
            excluded_sections=_TEAM_EXCLUDED,
        ),
        "main_quest": execution.get("main_quest"),
        "quests": {
            "blocked": _quests("blocked_quests"),
            "overdue": _quests("overdue_quests"),
            "ownerless": _quests("ownerless_quests"),
            "stale": _quests("stale_quests"),
            "side": _quests("side_quests"),
        },
        "project_health": execution.get("project_health", []),
        # Operational load only — open/stale/overdue per person, no ranking.
        "team_load": {
            "people": team.get("people", []),
            "unassigned": team.get("unassigned", {}),
        },
        "ownership_gaps": _redact_findings(
            team.get("ownership_gaps", []), SCOPE_TEAM
        ),
        "decisions_needed": decisions_needed,
        "product_work": product_work,
        "counts": {
            "blocked": len(execution.get("blocked_quests", [])),
            "overdue": len(execution.get("overdue_quests", [])),
            "ownerless": len(execution.get("ownerless_quests", [])),
            "stale": len(execution.get("stale_quests", [])),
            "decisions_needed": len(decisions_needed),
            "ownership_gaps": len(team.get("ownership_gaps", [])),
        },
    }


# --------------------------------------------------------------------------
# investor view
# --------------------------------------------------------------------------

_INVESTOR_HEALTH_HEADLINE = {
    "green": "Идём по плану",
    "yellow": "Есть зоны внимания",
    "red": "Есть критические зоны",
    "unknown": "Данные ещё собираются",
}

# High-level, sanitized risk categories — never raw finding summaries.
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


def _availability_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    return {(r["metric_key"], r["scope"]): r["status"] for r in rows}


def _observed_or_declared(
    *, value: Any, ready: bool
) -> str:
    return "observed" if ready and value not in (None, 0) else "declared_collecting"


async def build_investor_view(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Curated executive summary for investors — no finance, no leaks.

    Every claim is tagged ``observed`` (real data) or ``declared``
    (stated, evidence still collecting). No raw evidence/source refs, no
    internal notes, no people/stamina detail, no graph hygiene, no money.
    """

    safe_now = now or datetime.now(timezone.utc)

    overview = await build_founder_overview(now=safe_now)
    availability = await get_availability(session)
    avail = _availability_index(availability)

    status_level = str(overview.get("status", {}).get("level") or "unknown")
    projects = overview.get("projects", [])
    metrics = overview.get("metrics", {})

    # --- company snapshot (declared story + high-level health) ----------
    company_decl = (await get_declaration(session, key=KEY_COMPANY) or {}).get(
        "payload"
    ) or {}
    company_snapshot = {
        "headline": company_decl.get("oneliner") or None,
        "subline": company_decl.get("sub") or None,
        "business_model": [str(x) for x in (company_decl.get("model") or [])][:5],
        "health": status_level,
        "health_headline": _INVESTOR_HEALTH_HEADLINE.get(
            status_level, _INVESTOR_HEALTH_HEADLINE["unknown"]
        ),
        "active_areas": len(projects),
        "as_of": safe_now.date().isoformat(),
    }

    # --- product progress (per area, aggregated, no issue detail) -------
    product_progress = []
    total_done = total_all = 0
    for project in projects:
        jira = project.get("jira", {}) or {}
        total = int(jira.get("total") or 0)
        done = int(jira.get("done") or 0)
        if total <= 0:
            continue
        total_done += done
        total_all += total
        ready = avail.get(("jira.done", project.get("entity_id", ""))) == STATUS_READY
        product_progress.append(
            {
                "area": project.get("name"),
                "progress_pct": round(done / total * 100),
                "health": project.get("color"),
                "basis": "observed" if ready else "declared_collecting",
            }
        )
    overall_progress_pct = round(total_done / total_all * 100) if total_all else None

    # --- traction (never finance) ---------------------------------------
    def _traction(label: str, value: Any, key: str, scope: str) -> dict[str, Any]:
        ready = avail.get((key, scope)) == STATUS_READY
        return {
            "label": label,
            "value": value if ready else None,
            "basis": _observed_or_declared(value=value, ready=ready),
            "availability": avail.get((key, scope), "no_data"),
        }

    traction = [
        _traction("Слито PR (период)", metrics.get("prs_merged"),
                  "code.merged_prs", GLOBAL_SCOPE),
        _traction("Коммитов за 7 дней", metrics.get("commits_7d"),
                  "code.commits_7d", GLOBAL_SCOPE),
        _traction("Активность из источников", metrics.get("attention_items"),
                  "activity.events", GLOBAL_SCOPE),
        _traction("Документов в базе знаний", metrics.get("documents"),
                  "knowledge.tasks", GLOBAL_SCOPE),
    ]

    # --- declared 30/60/90 roadmap --------------------------------------
    roadmap_decl = (await get_declaration(session, key=KEY_ROADMAP) or {}).get(
        "payload"
    ) or {}
    horizons: dict[str, list[str]] = {"30": [], "60": [], "90": []}
    for item in roadmap_decl.get("items") or []:
        horizon = str(item.get("horizon") or "").strip()
        text = str(item.get("text") or "").strip()
        if horizon in horizons and text:
            horizons[horizon].append(text)
    roadmap = [
        {"horizon": h, "items": horizons[h], "basis": "declared"}
        for h in ("30", "60", "90")
    ]

    # --- key risks (category + count + severity, no raw summaries) ------
    # Audience-correct: only investor-scoped findings contribute. Founder /
    # team findings (incl. their counts) must never reach an investor, so we
    # filter at the source rather than aggregating across all scopes.
    investor_findings = await list_findings(
        session,
        status=STATUS_OPEN,
        visibility_scope=SCOPE_INVESTOR,
        limit=200,
    )
    risk_buckets: dict[str, dict[str, Any]] = {}
    for finding in investor_findings:
        ftype = finding.get("finding_type")
        label = _RISK_CATEGORY_LABELS.get(ftype)
        if not label:
            continue
        bucket = risk_buckets.setdefault(
            ftype, {"category": label, "count": 0, "severity": "low"}
        )
        bucket["count"] += 1
        if _SEVERITY_RANK.get(finding.get("severity"), 3) < _SEVERITY_RANK.get(
            bucket["severity"], 3
        ):
            bucket["severity"] = finding.get("severity")
    key_risks = sorted(
        risk_buckets.values(),
        key=lambda r: (_SEVERITY_RANK.get(r["severity"], 3), -r["count"]),
    )[:5]

    # --- what changed (evidence-backed global deltas only) --------------
    what_changed: list[dict[str, Any]] = []
    for key, label in (
        ("activity.events", "Активность из источников"),
        ("knowledge.tasks", "Задачи в базе знаний"),
        ("knowledge.decisions", "Зафиксированные решения"),
    ):
        if avail.get((key, GLOBAL_SCOPE)) != STATUS_READY:
            continue
        points = await metric_series(
            session, metric_key=key, scope=GLOBAL_SCOPE, days=14
        )
        if len(points) < 2:
            continue
        delta = (points[-1]["value"] or 0) - (points[0]["value"] or 0)
        if delta:
            what_changed.append(
                {
                    "label": label,
                    "delta": delta,
                    "direction": "up" if delta > 0 else "down",
                    "basis": "observed",
                }
            )

    # --- evidence-backed claims -----------------------------------------
    claims: list[dict[str, Any]] = []
    if overall_progress_pct is not None:
        jira_done_ready = any(
            avail.get(("jira.done", p.get("entity_id", ""))) == STATUS_READY
            for p in projects
        )
        claims.append(
            {
                "claim": f"Закрыто {overall_progress_pct}% задач по продукту",
                "basis": "observed" if jira_done_ready else "declared_collecting",
            }
        )
    for t in traction:
        if t["basis"] == "observed":
            claims.append(
                {"claim": f"{t['label']}: {t['value']}", "basis": "observed"}
            )
    # Declared roadmap items are claims still collecting evidence.
    for horizon in roadmap:
        for item in horizon["items"]:
            claims.append(
                {
                    "claim": f"{horizon['horizon']}д: {item}",
                    "basis": "declared_collecting",
                }
            )

    # --- open questions (from declared hypotheses still in flight) ------
    hyp_decl = (await get_declaration(session, key=KEY_HYPOTHESES) or {}).get(
        "payload"
    ) or {}
    open_questions = []
    for item in hyp_decl.get("items") or []:
        text = str(item.get("text") or "").strip()
        status = str(item.get("status") or "").strip()
        if text and status in {"testing", "risk"}:
            prefix = "Под вопросом" if status == "risk" else "Проверяем"
            open_questions.append(f"{prefix}: {text}")
    open_questions = open_questions[:6]

    # --- ask / next milestone (declared free text only) -----------------
    ask_decl = (await get_declaration(session, key=KEY_ASK) or {}).get(
        "payload"
    ) or {}
    ask = None
    if ask_decl.get("ask") or ask_decl.get("milestone"):
        ask = {
            "ask": ask_decl.get("ask") or None,
            # Investor-facing "what the raise funds" — named unambiguously
            # so it can never be confused with an internal/private note.
            "use_of_funds": (
                ask_decl.get("use_of_funds") or ask_decl.get("note") or None
            ),
            "milestone": ask_decl.get("milestone") or None,
            "basis": "declared",
        }

    return {
        "role": "investor",
        "generated_at": safe_now.isoformat(),
        "redaction_manifest": redaction_manifest(
            SCOPE_INVESTOR,
            included_sections=_INVESTOR_SECTIONS,
            excluded_sections=_INVESTOR_EXCLUDED,
        ),
        "company_snapshot": company_snapshot,
        "product_progress": {
            "areas": product_progress,
            "overall_progress_pct": overall_progress_pct,
        },
        "traction": traction,
        "roadmap": roadmap,
        "key_risks": key_risks,
        "what_changed": what_changed,
        "evidence_backed_claims": claims[:12],
        "open_questions": open_questions,
        "ask": ask,
    }
