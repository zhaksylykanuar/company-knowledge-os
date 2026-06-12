"""Second opinion layer: declared-vs-observed conflicts as first-class data.

This is the central feed of the product. Findings are produced by the
scanner from persisted read models (status snapshots today; meeting,
email-thread and hypothesis agents will add their own types later),
deduped by ``finding_key``, and live through a lifecycle the founder
controls: open -> accepted / dismissed / resolved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.second_opinion_models import SecondOpinionFinding
from app.services.confidence import build_confidence
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


async def list_findings(
    session: AsyncSession,
    *,
    status: str | None = STATUS_OPEN,
    finding_type: str | None = None,
    visibility_scope: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = select(SecondOpinionFinding).order_by(
        SecondOpinionFinding.severity.desc(),
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
    rows = (await session.execute(query.limit(limit))).scalars()
    return [
        {
            "finding_key": row.finding_key,
            "entity_id": row.entity_id,
            "finding_type": row.finding_type,
            "declared_state": row.declared_state,
            "observed_state": row.observed_state,
            "summary": row.summary,
            "severity": row.severity,
            "confidence": row.confidence,
            "confidence_factors": row.confidence_factors,
            "evidence_refs": row.evidence_refs,
            "source_refs": row.source_refs,
            "status": row.status,
            "visibility_scope": row.visibility_scope,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def set_finding_status(
    session: AsyncSession,
    *,
    finding_key: str,
    status: str,
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
    row.resolved_at = (
        datetime.now(timezone.utc) if status == STATUS_RESOLVED else None
    )
    await session.flush()
    return {"finding_key": row.finding_key, "status": row.status}


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
) -> dict[str, int]:
    """Project latest status snapshots into findings (idempotent)."""

    from app.db.graph_models import EntityRecord

    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    projects = (
        await session.execute(
            select(EntityRecord).where(
                EntityRecord.entity_type == ENTITY_TYPE_PROJECT
            )
        )
    ).scalars()

    async def emit(outcome: str) -> None:
        counts[outcome] += 1

    for project in projects:
        snapshot = await get_latest_status_snapshot(
            session,
            organization_id=organization_id,
            entity_type=ENTITY_TYPE_PROJECT,
            entity_id=project.entity_id,
        )
        if snapshot is None:
            continue
        source_refs = [
            {"kind": "status_snapshot", "snapshot_id": snapshot.id},
            {"kind": "project", "entity_id": project.entity_id},
        ]
        quality = float(snapshot.confidence or 0.5)

        for item in snapshot.blockers_json or []:
            score, factors = build_confidence(
                evidence_count=1,
                source_quality=quality,
                freshness=0.9,
                cross_source_match=False,
            )
            await emit(
                await upsert_finding(
                    session,
                    finding_key=f"{project.entity_id}:delivery_risk:{item.get('id')}",
                    entity_id=project.entity_id,
                    finding_type=FINDING_DELIVERY_RISK,
                    declared_state=(
                        f"Срок задачи: {item.get('due_date') or 'задан'}"
                    ),
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
            )

        for item in snapshot.conflicts_json or []:
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
            await emit(
                await upsert_finding(
                    session,
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
            )

        for item in snapshot.risks_json or []:
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
            await emit(
                await upsert_finding(
                    session,
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
            )

    return counts
