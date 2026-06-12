"""Second opinion layer: declared-vs-observed conflicts as first-class data.

This is the central feed of the product. Findings are produced by the
scanner from persisted read models (status snapshots today; meeting,
email-thread and hypothesis agents will add their own types later),
deduped by ``finding_key``, and live through a lifecycle the founder
controls: open -> accepted / dismissed / resolved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.second_opinion_models import SecondOpinionFinding
from app.services.confidence import build_confidence, explain_confidence
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.status_engine import DEFAULT_ORGANIZATION_ID
from app.services.status_snapshot_repository import get_latest_status_snapshot

FINDING_EXECUTION_MISMATCH = "execution_mismatch"
FINDING_FOCUS_DRIFT = "focus_drift"
FINDING_STALE_CLAIM = "stale_claim"
FINDING_EVIDENCE_CONTRADICTION = "evidence_contradiction"
FINDING_OWNERSHIP_GAP = "ownership_gap"
FINDING_COMMUNICATION_SILENCE = "communication_silence"
FINDING_DELIVERY_RISK = "delivery_risk"
FINDING_VALIDATION_GAP = "validation_gap"

FINDING_TYPES = frozenset(
    {
        FINDING_EXECUTION_MISMATCH,
        FINDING_FOCUS_DRIFT,
        FINDING_STALE_CLAIM,
        FINDING_EVIDENCE_CONTRADICTION,
        FINDING_OWNERSHIP_GAP,
        FINDING_COMMUNICATION_SILENCE,
        FINDING_DELIVERY_RISK,
        FINDING_VALIDATION_GAP,
    }
)

STATUS_OPEN = "open"
STATUS_ACCEPTED = "accepted"
STATUS_DISMISSED = "dismissed"
STATUS_RESOLVED = "resolved"
FINDING_STATUSES = frozenset(
    {STATUS_OPEN, STATUS_ACCEPTED, STATUS_DISMISSED, STATUS_RESOLVED}
)

SEVERITIES = ("low", "medium", "high")

VISIBILITY_FOUNDER = "founder"
VISIBILITY_TEAM = "team"
VISIBILITY_INVESTOR = "investor"

# What the founder should do about each conflict type — shown in the feed.
SUGGESTED_ACTIONS = {
    FINDING_EXECUTION_MISMATCH: (
        "Спросить владельца задачи, что реально происходит, и привести Jira "
        "в соответствие с кодом"
    ),
    FINDING_FOCUS_DRIFT: "Сверить активность команды с фокусом недели",
    FINDING_STALE_CLAIM: "Обновить или закрыть устаревшую задачу",
    FINDING_EVIDENCE_CONTRADICTION: "Перепроверить заявление против evidence",
    FINDING_OWNERSHIP_GAP: "Назначить ответственного",
    FINDING_COMMUNICATION_SILENCE: "Написать контакту — диалог затих",
    FINDING_DELIVERY_RISK: "Передоговорить срок или разблокировать задачу сегодня",
    FINDING_VALIDATION_GAP: "Запланировать проверку гипотезы",
}


async def upsert_finding(
    session: AsyncSession,
    *,
    finding_key: str,
    company_id: str = DEFAULT_ORGANIZATION_ID,
    entity_id: str | None,
    finding_type: str,
    declared_state: str,
    observed_state: str,
    summary: str,
    severity: str,
    confidence: float,
    confidence_factors: dict[str, Any] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    visibility_scope: str = VISIBILITY_FOUNDER,
) -> str:
    """Create or refresh a finding. Dismissed/resolved keys are left alone.

    Returns one of: created / updated / unchanged / skipped.
    """

    if finding_type not in FINDING_TYPES:
        raise ValueError(f"unknown finding type: {finding_type}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity}")

    row = await session.scalar(
        select(SecondOpinionFinding).where(
            SecondOpinionFinding.finding_key == finding_key
        )
    )
    if row is None:
        session.add(
            SecondOpinionFinding(
                finding_key=finding_key,
                company_id=company_id,
                entity_id=entity_id,
                finding_type=finding_type,
                declared_state=declared_state,
                observed_state=observed_state,
                summary=summary,
                severity=severity,
                confidence=confidence,
                confidence_factors=confidence_factors,
                evidence_refs=list(evidence_refs or []),
                source_refs=list(source_refs or []),
                status=STATUS_OPEN,
                visibility_scope=visibility_scope,
            )
        )
        await session.flush()
        return "created"

    if row.status in {STATUS_DISMISSED, STATUS_RESOLVED}:
        return "skipped"

    changed = (
        row.declared_state != declared_state
        or row.observed_state != observed_state
        or row.summary != summary
        or row.severity != severity
    )
    if not changed:
        return "unchanged"
    row.declared_state = declared_state
    row.observed_state = observed_state
    row.summary = summary
    row.severity = severity
    row.confidence = confidence
    row.confidence_factors = confidence_factors
    row.evidence_refs = list(evidence_refs or [])
    await session.flush()
    return "updated"


def _severity_order_expression():
    return case(
        (SecondOpinionFinding.severity == "high", 0),
        (SecondOpinionFinding.severity == "medium", 1),
        else_=2,
    )


async def list_findings(
    session: AsyncSession,
    *,
    status: str | None = STATUS_OPEN,
    finding_type: str | None = None,
    visibility_scope: str | None = None,
    include_snoozed: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = select(SecondOpinionFinding).order_by(
        _severity_order_expression(),
        SecondOpinionFinding.created_at.desc(),
    )
    if status is not None:
        query = query.where(SecondOpinionFinding.status == status)
    if finding_type is not None:
        query = query.where(SecondOpinionFinding.finding_type == finding_type)
    if visibility_scope is not None:
        query = query.where(
            SecondOpinionFinding.visibility_scope == visibility_scope
        )
    if not include_snoozed:
        now = datetime.now(timezone.utc)
        query = query.where(
            (SecondOpinionFinding.snoozed_until.is_(None))
            | (SecondOpinionFinding.snoozed_until <= now)
        )
    rows = (await session.execute(query.limit(limit))).scalars()
    return [_finding_read_model(row) for row in rows]


def _finding_read_model(row: SecondOpinionFinding) -> dict[str, Any]:
    return {
        "finding_key": row.finding_key,
        "entity_id": row.entity_id,
        "finding_type": row.finding_type,
        "declared_state": row.declared_state,
        "observed_state": row.observed_state,
        "summary": row.summary,
        "severity": row.severity,
        "confidence": row.confidence,
        "confidence_factors": row.confidence_factors,
        "confidence_hint": explain_confidence(
            row.confidence, row.confidence_factors or {}
        ),
        "suggested_action": SUGGESTED_ACTIONS.get(row.finding_type, ""),
        "evidence_refs": row.evidence_refs,
        "source_refs": row.source_refs,
        "status": row.status,
        "visibility_scope": row.visibility_scope,
        "note": row.note,
        "snoozed_until": row.snoozed_until.isoformat()
        if row.snoozed_until
        else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def set_finding_status(
    session: AsyncSession,
    *,
    finding_key: str,
    status: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    if status not in FINDING_STATUSES:
        raise ValueError(f"unknown finding status: {status}")
    row = await session.scalar(
        select(SecondOpinionFinding).where(
            SecondOpinionFinding.finding_key == finding_key
        )
    )
    if row is None:
        return None
    row.status = status
    if note is not None:
        row.note = note[:500]
    row.resolved_at = (
        datetime.now(timezone.utc) if status == STATUS_RESOLVED else None
    )
    await session.flush()
    return {"finding_key": row.finding_key, "status": row.status}


async def snooze_finding(
    session: AsyncSession,
    *,
    finding_key: str,
    days: int = 7,
) -> dict[str, Any] | None:
    """Hide an open finding from the feed for N days without deciding."""

    row = await session.scalar(
        select(SecondOpinionFinding).where(
            SecondOpinionFinding.finding_key == finding_key
        )
    )
    if row is None:
        return None
    row.snoozed_until = datetime.now(timezone.utc) + timedelta(
        days=max(1, min(int(days), 90))
    )
    await session.flush()
    return {
        "finding_key": row.finding_key,
        "snoozed_until": row.snoozed_until.isoformat(),
    }


async def set_finding_note(
    session: AsyncSession,
    *,
    finding_key: str,
    note: str,
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(SecondOpinionFinding).where(
            SecondOpinionFinding.finding_key == finding_key
        )
    )
    if row is None:
        return None
    row.note = note[:500]
    await session.flush()
    return {"finding_key": row.finding_key, "note": row.note}


_CONFLICT_TYPE_MAP = {
    "jira_in_progress_without_code": (
        FINDING_EXECUTION_MISMATCH,
        "Jira: задача In Progress",
        "Свежей код-активности по задаче нет (коммиты и PR за 7 дней)",
    ),
    "github_pr_without_jira": (
        FINDING_EXECUTION_MISMATCH,
        "GitHub: PR открыт",
        "PR не привязан ни к одной Jira-задаче",
    ),
    "merged_pr_open_jira": (
        FINDING_STALE_CLAIM,
        "Jira: задача всё ещё открыта",
        "PR по этой задаче уже смержен",
    ),
}

_RISK_TYPE_MAP = {
    "stale_issue": (
        FINDING_STALE_CLAIM,
        "Jira: задача числится в работе",
        "Задача без движения больше 14 дней",
        "medium",
    ),
    "missing_owner": (
        FINDING_OWNERSHIP_GAP,
        "Jira: задача открыта",
        "У задачи нет ответственного",
        "low",
    ),
    "stale_review_pr": (
        FINDING_DELIVERY_RISK,
        "GitHub: PR ждёт ревью",
        "Ревью стоит больше 2 дней",
        "medium",
    ),
}


async def scan_second_opinion(
    session: AsyncSession,
    *,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    now: datetime | None = None,
) -> dict[str, int]:
    """Build fresh project status snapshots and project them into findings.

    The scanner rebuilds snapshots itself (same building blocks as the
    bot) instead of trusting the latest persisted row: tests and stale
    runs may have saved snapshots with a synthetic clock, and findings
    must never inherit somebody else's "now".
    """

    from app.db.graph_models import EntityRecord
    from app.services.github_graph_mapping import repos_for_project
    from app.services.jira_graph_mapping import jira_keys_for_project
    from app.services.project_status_view import (
        load_project_issue_snapshots,
        load_repo_activity,
    )
    from app.services.status_engine import build_project_status_snapshot
    from app.services.status_snapshot_repository import save_status_snapshot

    safe_now = now or datetime.now(timezone.utc)
    counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "auto_resolved": 0,
    }
    emitted_keys: set[str] = set()
    scanned_projects: list[str] = []

    projects = (
        await session.execute(
            select(EntityRecord).where(
                EntityRecord.entity_type == ENTITY_TYPE_PROJECT
            )
        )
    ).scalars()

    async def record(**kwargs: Any) -> None:
        emitted_keys.add(kwargs["finding_key"])
        counts[await upsert_finding(session, **kwargs)] += 1

    for project in projects:
        scanned_projects.append(project.entity_id)
        jira_keys = await jira_keys_for_project(session, project.entity_id)
        issue_snapshots = await load_project_issue_snapshots(session, jira_keys)
        repos = await repos_for_project(session, project.entity_id)
        repo_activity = await load_repo_activity(session, repos, now=safe_now)
        previous = await get_latest_status_snapshot(
            session,
            organization_id=organization_id,
            entity_type=ENTITY_TYPE_PROJECT,
            entity_id=project.entity_id,
        )
        snapshot = build_project_status_snapshot(
            project_entity_id=project.entity_id,
            project_name=project.canonical_name,
            jira_keys=jira_keys,
            snapshots=issue_snapshots,
            repo_activity=repo_activity,
            previous_snapshot=previous,
            organization_id=organization_id,
            now=safe_now,
        )
        saved = await save_status_snapshot(session, snapshot)
        source_refs = [
            {"kind": "status_snapshot", "snapshot_id": getattr(saved, "id", None)},
            {"kind": "project", "entity_id": project.entity_id},
        ]
        quality = float(snapshot.confidence or 0.5)

        for item in snapshot.blockers or ():
            score, factors = build_confidence(
                evidence_count=1,
                source_quality=quality,
                freshness=0.9,
                cross_source_match=False,
            )
            await record(
                finding_key=f"{project.entity_id}:delivery_risk:{item.get('id')}",
                entity_id=project.entity_id,
                finding_type=FINDING_DELIVERY_RISK,
                declared_state=f"Срок задачи: {item.get('due_date') or 'задан'}",
                observed_state="Срок прошёл, задача всё ещё открыта",
                summary=(
                    f"[{item.get('source_id')}] {str(item.get('title'))[:140]}"
                ),
                severity="high",
                confidence=score,
                confidence_factors=factors,
                evidence_refs=[dict(item)],
                source_refs=source_refs,
            )

        for item in snapshot.conflicts or ():
            mapping = _CONFLICT_TYPE_MAP.get(str(item.get("type")))
            if mapping is None:
                continue
            finding_type, declared, observed = mapping
            score, factors = build_confidence(
                evidence_count=2,
                source_quality=quality,
                freshness=0.9,
                cross_source_match=True,
            )
            await record(
                finding_key=f"{project.entity_id}:{item.get('id')}",
                entity_id=project.entity_id,
                finding_type=finding_type,
                declared_state=f"{declared}: {item.get('source_id')}",
                observed_state=observed,
                summary=(
                    f"[{item.get('source_id')}] {str(item.get('title'))[:140]}"
                ),
                severity=str(item.get("severity") or "medium"),
                confidence=score,
                confidence_factors=factors,
                evidence_refs=[dict(item)],
                source_refs=source_refs,
            )

        for item in snapshot.risks or ():
            mapping = _RISK_TYPE_MAP.get(str(item.get("type")))
            if mapping is None:
                continue
            finding_type, declared, observed, severity = mapping
            score, factors = build_confidence(
                evidence_count=1,
                source_quality=quality,
                freshness=0.7,
                cross_source_match=False,
            )
            await record(
                finding_key=f"{project.entity_id}:{item.get('id')}",
                entity_id=project.entity_id,
                finding_type=finding_type,
                declared_state=declared,
                observed_state=(
                    observed
                    + (
                        f" (уже {item.get('age_days')} дн)"
                        if item.get("age_days")
                        else ""
                    )
                ),
                summary=(
                    f"[{item.get('source_id')}] {str(item.get('title'))[:140]}"
                ),
                severity=severity,
                confidence=score,
                confidence_factors=factors,
                evidence_refs=[dict(item)],
                source_refs=source_refs,
            )

    # Reconciliation: an open finding the scanner no longer observes is a
    # disappeared conflict — auto-resolve it instead of leaving an orphan.
    scanner_types = (
        {FINDING_DELIVERY_RISK}
        | {mapping[0] for mapping in _CONFLICT_TYPE_MAP.values()}
        | {mapping[0] for mapping in _RISK_TYPE_MAP.values()}
    )
    if scanned_projects:
        open_rows = (
            await session.execute(
                select(SecondOpinionFinding)
                .where(SecondOpinionFinding.status == STATUS_OPEN)
                .where(SecondOpinionFinding.entity_id.in_(scanned_projects))
                .where(SecondOpinionFinding.finding_type.in_(scanner_types))
            )
        ).scalars()
        for row in open_rows:
            if row.finding_key in emitted_keys:
                continue
            row.status = STATUS_RESOLVED
            row.resolved_at = safe_now
            if not row.note:
                row.note = "auto: конфликт исчез при повторном скане"
            counts["auto_resolved"] += 1
        await session.flush()

    return counts
