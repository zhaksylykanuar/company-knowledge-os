"""Operating rhythm read models: weekly review, daily check, decision review.

A regular cadence over the existing trust layer — no new automation, just
honest aggregation of what already happened: what changed, what is stuck,
which claims the second opinion sees differently, which decisions wait,
what closed, what was deferred and what became a risk.

Every finding is redacted for the viewer scope, so the team cadence never
shows founder-only conclusions, private notes or raw source refs. The
decision review (pending inbox decisions + audit trail) is founder-only
and gated at the API layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.second_opinion_models import SecondOpinionFinding
from app.services.action_center import (
    GROUP_CRITICAL,
    GROUP_DECISION,
    build_action_center,
)
from app.services.agent_run_log import latest_runs
from app.services.data_availability import get_availability
from app.services.execution_view import build_execution_view
from app.services.inbox import build_inbox
from app.services.inbox_audit import list_recent_inbox_actions
from app.services.metric_collector import GLOBAL_SCOPE, metric_series
from app.services.second_opinion import (
    STATUS_OPEN,
    _finding_read_model,
)
from app.services.visibility import SCOPE_FOUNDER, SCOPE_TEAM, redact_finding

WEEKLY_WINDOW_DAYS = 7
DAILY_WINDOW_HOURS = 24

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_CONFLICT_TYPES = {"execution_mismatch", "focus_drift", "evidence_contradiction"}


def _redact(findings: list[dict[str, Any]], viewer_scope: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for finding in findings:
        redacted = redact_finding(finding, viewer_scope)
        if redacted is not None:
            out.append(redacted)
    return out


def _redact_quests(
    quests: list[dict[str, Any]], viewer_scope: str
) -> list[dict[str, Any]]:
    """Redact the findings attached to each quest for the viewer scope."""

    out: list[dict[str, Any]] = []
    for quest in quests:
        safe = dict(quest)
        safe_findings = _redact(quest.get("findings", []), viewer_scope)
        safe["findings"] = safe_findings
        safe["evidence_count"] = len(safe_findings)
        out.append(safe)
    return out


# Action sources a non-founder viewer may see in "today's actions": their
# own execution work and team-scoped conflicts only (never founder-scoped
# sales/relationship signals, graph hygiene or data-ops).
def _team_safe_action(action: dict[str, Any]) -> bool:
    source = action.get("source")
    if source == "execution":
        return True
    if source == "second_opinion":
        return action.get("visibility") == SCOPE_TEAM
    return False


async def _findings_since(
    session: AsyncSession, *, since: datetime
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.created_at >= since)
            .order_by(
                SecondOpinionFinding.created_at.desc(),
                SecondOpinionFinding.finding_key,
            )
        )
    ).scalars()
    return [_finding_read_model(row) for row in rows]


async def _open_findings(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == STATUS_OPEN)
            .order_by(SecondOpinionFinding.finding_key)
        )
    ).scalars()
    return [_finding_read_model(row) for row in rows]


async def _snoozed_findings(
    session: AsyncSession, *, now: datetime
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(
                SecondOpinionFinding.snoozed_until.is_not(None),
                SecondOpinionFinding.snoozed_until > now,
            )
            .order_by(SecondOpinionFinding.finding_key)
        )
    ).scalars()
    return [_finding_read_model(row) for row in rows]


async def _global_deltas(session: AsyncSession) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for key, label in (
        ("activity.events", "Активность из источников"),
        ("knowledge.tasks", "Задачи в базе знаний"),
        ("knowledge.risks", "Риски в базе знаний"),
        ("knowledge.decisions", "Зафиксированные решения"),
    ):
        points = await metric_series(
            session, metric_key=key, scope=GLOBAL_SCOPE, days=WEEKLY_WINDOW_DAYS + 1
        )
        if len(points) < 2:
            continue
        delta = (points[-1]["value"] or 0) - (points[0]["value"] or 0)
        if delta:
            changed.append(
                {
                    "label": label,
                    "delta": delta,
                    "direction": "up" if delta > 0 else "down",
                }
            )
    return changed


async def build_weekly_review(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    viewer_scope: str = SCOPE_FOUNDER,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    since = safe_now - timedelta(days=WEEKLY_WINDOW_DAYS)

    execution = await build_execution_view(session, now=safe_now)
    open_findings = await _open_findings(session)
    new_findings = await _findings_since(session, since=since)
    snoozed = await _snoozed_findings(session, now=safe_now)
    runs = await latest_runs(session, limit=40)
    inbox = await build_inbox(session, limit=60)
    deltas = await _global_deltas(session)

    new_evidence = sum(
        int(r.get("created") or 0) + int(r.get("updated_from_new_evidence") or 0)
        for r in runs
    )

    ai_sees = _redact(
        [f for f in open_findings if f.get("finding_type") in _CONFLICT_TYPES],
        viewer_scope,
    )
    decisions_needed = _redact(
        [
            f
            for f in open_findings
            if f.get("finding_type")
            in {"execution_mismatch", "delivery_risk", "ownership_gap"}
        ],
        viewer_scope,
    )
    new_risks = _redact(
        sorted(
            [f for f in new_findings if f.get("severity") == "high"],
            # Explicit finding_key tiebreaker keeps ordering deterministic
            # (a curated weekly update hashes this list).
            key=lambda f: (
                _SEVERITY_RANK.get(f.get("severity"), 3),
                f.get("finding_key") or "",
            ),
        ),
        viewer_scope,
    )

    # Closed work (audit) is founder-only; team sees a count. Filter at the
    # SQL level so unrelated audit writes (e.g. an update approval) cannot
    # shift this window and perturb a curated-update content hash.
    closed = await list_recent_inbox_actions(
        session,
        since=since,
        actions=("finding_status", "proposal_decision"),
        limit=50,
    )

    return {
        "role": viewer_scope,
        "cadence": "weekly",
        "generated_at": safe_now.isoformat(),
        "window_days": WEEKLY_WINDOW_DAYS,
        "what_changed": {
            "metric_deltas": deltas,
            "new_evidence_processed": new_evidence,
        },
        "stuck": {
            "blocked": _redact_quests(
                execution.get("blocked_quests", [])[:8], viewer_scope
            ),
            "blocked_count": execution.get("counts", {}).get("blocked", 0),
            "stale_count": execution.get("counts", {}).get("stale", 0),
            "overdue_count": execution.get("counts", {}).get("overdue", 0),
        },
        "ai_sees_differently": ai_sees[:12],
        "decisions_needed": {
            "findings": decisions_needed[:12],
            "pending_proposals": inbox.get("counts", {}).get("proposals", 0),
        },
        "closed": {
            "count": len(closed),
            "items": closed[:12] if viewer_scope == SCOPE_FOUNDER else [],
        },
        "deferred": _redact(snoozed, viewer_scope)[:12],
        "new_risks": new_risks[:12],
        "counts": {
            "ai_sees_differently": len(ai_sees),
            "decisions_needed": len(decisions_needed),
            "deferred": len(snoozed),
            "new_risks": len(new_risks),
            "closed": len(closed),
        },
    }


async def build_daily_check(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    viewer_scope: str = SCOPE_FOUNDER,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    since = safe_now - timedelta(hours=DAILY_WINDOW_HOURS)

    execution = await build_execution_view(session, now=safe_now)
    new_findings = await _findings_since(session, since=since)
    open_findings = await _open_findings(session)
    runs = await latest_runs(session, limit=20)
    availability = await get_availability(session)
    center = await build_action_center(session, now=safe_now, limit=60)

    new_evidence = sum(
        int(r.get("created") or 0) + int(r.get("updated_from_new_evidence") or 0)
        for r in runs
        if (r.get("run_finished_at") or "") >= since.isoformat()
    )

    new_conflicts = _redact(new_findings, viewer_scope)
    stale_comm = _redact(
        [f for f in open_findings if f.get("finding_type") == "communication_silence"],
        viewer_scope,
    )
    # Today's actions: the two most pressing priority groups. Non-founder
    # viewers only see their own execution work + team-scoped conflicts.
    actions_today: list[dict[str, Any]] = []
    for group in center.get("groups", []):
        if group["key"] in {GROUP_CRITICAL, GROUP_DECISION}:
            actions_today.extend(group["actions"])
    if viewer_scope != SCOPE_FOUNDER:
        actions_today = [a for a in actions_today if _team_safe_action(a)]
    data_issues = [
        r for r in availability if r["status"] in {"stale", "no_data"}
    ]

    return {
        "role": viewer_scope,
        "cadence": "daily",
        "generated_at": safe_now.isoformat(),
        "window_hours": DAILY_WINDOW_HOURS,
        "new_conflicts": new_conflicts[:12],
        "operational": {
            "blocked": execution.get("counts", {}).get("blocked", 0),
            "overdue": execution.get("counts", {}).get("overdue", 0),
            "ownerless": execution.get("counts", {}).get("ownerless", 0),
            "top_blocked": _redact_quests(
                execution.get("blocked_quests", [])[:5], viewer_scope
            ),
            "top_overdue": _redact_quests(
                execution.get("overdue_quests", [])[:5], viewer_scope
            ),
        },
        "new_evidence": new_evidence,
        "actions_for_today": actions_today[:10],
        "stale_communication": stale_comm[:8],
        "data_issues": [
            {
                "metric_key": r["metric_key"],
                "scope": r["scope"],
                "status": r["status"],
                "message": r["message"],
            }
            for r in data_issues[:12]
        ],
        "counts": {
            "new_conflicts": len(new_conflicts),
            "actions_for_today": len(actions_today),
            "stale_communication": len(stale_comm),
            "data_issues": len(data_issues),
        },
    }


async def build_decision_review(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Pending decisions + recent decisions + consequences + audit trail.

    Founder-only by contract (raw audit trail, proposal internals).
    """

    safe_now = now or datetime.now(timezone.utc)
    since = safe_now - timedelta(days=WEEKLY_WINDOW_DAYS)

    inbox = await build_inbox(session, limit=60)
    recent = await list_recent_inbox_actions(session, since=since, limit=50)

    decisions = [a for a in recent if a.get("action") == "proposal_decision"]
    consequences = []
    for action in decisions:
        nxt = action.get("next_state") or {}
        applied = nxt.get("applied") or {}
        consequences.append(
            {
                "target_id": action.get("target_id"),
                "decision": nxt.get("status"),
                "applied": applied,
                "actor": action.get("actor"),
                "reversible": action.get("reversible"),
                "created_at": action.get("created_at"),
            }
        )

    return {
        "role": SCOPE_FOUNDER,
        "cadence": "decision",
        "generated_at": safe_now.isoformat(),
        "pending": {
            "proposals": inbox.get("proposals", []),
            "identity_proposals": inbox.get("identity_proposals", []),
            "gardener_proposals": inbox.get("gardener_proposals", []),
            "disputed_links": inbox.get("disputed_links", []),
            "findings_open": inbox.get("counts", {}).get("findings_open", 0),
        },
        "recent_decisions": decisions[:20],
        "consequences": consequences[:20],
        "audit_trail": recent[:30],
        "counts": {
            "pending_proposals": inbox.get("counts", {}).get("proposals", 0),
            "pending_disputed_links": inbox.get("counts", {}).get(
                "disputed_links", 0
            ),
            "recent_decisions": len(decisions),
        },
    }
