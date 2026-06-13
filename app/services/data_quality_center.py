"""Data Quality Center read model.

Every item is derived from stored evidence/read-model rows. There is no
invented score: issues are grouped by explicit, explainable signals.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentRunLog, DataAvailability
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord, EntitySourceAccount
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.source_control import SOURCE_DEFINITIONS, connector_setup_status

_AVAILABILITY_GAP_STATUSES = {"no_data", "insufficient", "stale"}
_OPEN_REQUEST_STATUSES = {"requested", "accepted", "running"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue(
    *,
    category: str,
    severity: str,
    why_it_matters: str,
    affected_entity: str | None = None,
    affected_source: str | None = None,
    evidence_count: int = 1,
    confidence: float | None = None,
    suggested_action: str,
    cta: dict[str, Any],
    related_run_id: str | None = None,
    related_request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "why_it_matters": why_it_matters,
        "affected_entity": affected_entity,
        "affected_source": affected_source,
        "evidence_count": evidence_count,
        "confidence": confidence,
        "suggested_action": suggested_action,
        "cta": cta,
        "related_run_id": related_run_id,
        "related_request_id": related_request_id,
    }


async def build_data_quality_center(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or _now()
    issues: list[dict[str, Any]] = []

    availability_rows = (
        await session.execute(
            select(DataAvailability)
            .where(DataAvailability.status.in_(_AVAILABILITY_GAP_STATUSES))
            .order_by(DataAvailability.updated_at.desc())
            .limit(50)
        )
    ).scalars()
    for row in availability_rows:
        issues.append(
            _issue(
                category="data_availability_gap",
                severity="medium" if row.status == "stale" else "low",
                why_it_matters=row.message,
                affected_entity=row.scope,
                affected_source=row.metric_key.split(".", 1)[0],
                evidence_count=row.points_count,
                suggested_action="Подключить источник или обновить ingestion.",
                cta={
                    "target": "sources",
                    "source_type": row.metric_key.split(".", 1)[0],
                    "action": "open_source_control",
                },
            )
        )

    orphan_rows = (
        await session.execute(
            select(EntityRecord)
            .where(
                ~EntityRecord.entity_id.in_(
                    select(EntityLinkRecord.from_entity_id)
                )
            )
            .where(
                ~EntityRecord.entity_id.in_(
                    select(EntityLinkRecord.to_entity_id)
                )
            )
            .order_by(EntityRecord.created_at.desc())
            .limit(30)
        )
    ).scalars()
    for row in orphan_rows:
        issues.append(
            _issue(
                category="orphan_node",
                severity="low",
                why_it_matters="Нода графа не связана с другими сущностями, поэтому evidence может не попадать в проектный контекст.",
                affected_entity=row.entity_id,
                evidence_count=1,
                confidence=1.0,
                suggested_action="Проверить Graph Gardener proposals или связать ноду вручную через approved flow.",
                cta={"target": "inbox", "action": "review_graph_gardener"},
            )
        )

    low_edge_rows = (
        await session.execute(
            select(EntityLinkRecord)
            .where(EntityLinkRecord.confidence < 0.6)
            .order_by(EntityLinkRecord.created_at.desc())
            .limit(30)
        )
    ).scalars()
    for row in low_edge_rows:
        issues.append(
            _issue(
                category="low_confidence_edge",
                severity="medium",
                why_it_matters="Слабая связь может направлять evidence к неверному проекту или человеку.",
                affected_entity=f"{row.from_entity_id}->{row.to_entity_id}",
                evidence_count=len(row.evidence_refs or []),
                confidence=row.confidence,
                suggested_action="Подтвердить или отклонить связь в Inbox.",
                cta={"target": "inbox", "action": "review_link", "link_id": row.link_id},
            )
        )

    missing_owner_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.finding_type == "ownership_gap")
            .where(SecondOpinionFinding.status == "open")
            .order_by(SecondOpinionFinding.updated_at.desc())
            .limit(20)
        )
    ).scalars()
    for row in missing_owner_rows:
        issues.append(
            _issue(
                category="missing_owner",
                severity=row.severity,
                why_it_matters=row.summary,
                affected_entity=row.entity_id,
                evidence_count=len(row.evidence_refs or []),
                confidence=row.confidence,
                suggested_action="Назначить владельца через Action Center / Inbox.",
                cta={
                    "target": "action_center",
                    "action": "assign_owner",
                    "finding_key": row.finding_key,
                },
            )
        )

    findings_without_evidence = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(
                or_(
                    SecondOpinionFinding.evidence_refs.is_(None),
                    func.json_array_length(SecondOpinionFinding.evidence_refs) == 0,
                )
            )
            .order_by(SecondOpinionFinding.updated_at.desc())
            .limit(20)
        )
    ).scalars()
    for row in findings_without_evidence:
        issues.append(
            _issue(
                category="finding_without_evidence",
                severity="high",
                why_it_matters="Finding без evidence_refs нельзя проверить и безопасно показывать как факт.",
                affected_entity=row.entity_id,
                evidence_count=0,
                confidence=row.confidence,
                suggested_action="Пересобрать finding из source_events или скрыть до появления evidence.",
                cta={
                    "target": "second_opinion",
                    "action": "review_finding",
                    "finding_key": row.finding_key,
                },
            )
        )

    failed_runs = (
        await session.execute(
            select(AgentRunLog)
            .where(AgentRunLog.errors > 0)
            .order_by(AgentRunLog.created_at.desc())
            .limit(20)
        )
    ).scalars()
    for row in failed_runs:
        issues.append(
            _issue(
                category="failed_normalization",
                severity="high",
                why_it_matters=f"Agent run {row.agent} reported {row.errors} errors.",
                affected_source=row.agent,
                evidence_count=row.errors,
                suggested_action="Открыть run details и устранить причину ошибки до следующего sync.",
                cta={"target": "agent_runs", "action": "view_run", "run_id": row.run_id},
            )
        )

    duplicate_accounts = (
        await session.execute(
            select(
                EntitySourceAccount.source_system,
                EntitySourceAccount.account_id,
                func.count(EntitySourceAccount.id),
            )
            .group_by(EntitySourceAccount.source_system, EntitySourceAccount.account_id)
            .having(func.count(EntitySourceAccount.id) > 1)
            .limit(20)
        )
    ).all()
    for source_system, account_id, count in duplicate_accounts:
        issues.append(
            _issue(
                category="duplicate_account",
                severity="medium",
                why_it_matters="Один внешний аккаунт привязан к нескольким сущностям.",
                affected_source=str(source_system),
                affected_entity=str(account_id),
                evidence_count=int(count or 0),
                suggested_action="Проверить identity merge proposal.",
                cta={"target": "inbox", "action": "review_identity"},
            )
        )

    paused_sources = (
        await session.execute(
            select(SourceControlState).where(SourceControlState.paused.is_(True))
        )
    ).scalars()
    for row in paused_sources:
        issues.append(
            _issue(
                category="source_paused",
                severity="medium",
                why_it_matters="Источник поставлен на паузу, новые evidence не будут попадать в read-models.",
                affected_source=row.source_type,
                evidence_count=1,
                suggested_action="Resume source, если пауза больше не нужна.",
                cta={
                    "target": "sources",
                    "source_type": row.source_type,
                    "action": "resume",
                },
            )
        )

    pending_requests = (
        await session.execute(
            select(SourceRunRequest)
            .where(SourceRunRequest.status.in_(_OPEN_REQUEST_STATUSES))
            .order_by(SourceRunRequest.created_at.desc())
            .limit(30)
        )
    ).scalars()
    for row in pending_requests:
        issues.append(
            _issue(
                category="source_action_waiting_for_review",
                severity="low",
                why_it_matters="Source action requested but not executed by an approved operator flow.",
                affected_source=row.source_type,
                evidence_count=1,
                suggested_action="Review request before any external connector run.",
                cta={
                    "target": "sources",
                    "source_type": row.source_type,
                    "action": row.action_type,
                    "request_id": row.request_id,
                },
                related_run_id=row.run_id,
                related_request_id=row.request_id,
            )
        )

    states = {
        row.source_type: row
        for row in (await session.execute(select(SourceControlState))).scalars()
    }
    recent_requests = (
        await session.execute(
            select(SourceRunRequest)
            .order_by(SourceRunRequest.created_at.desc(), SourceRunRequest.id.desc())
            .limit(200)
        )
    ).scalars().all()
    by_source: dict[str, list[SourceRunRequest]] = {}
    for row in recent_requests:
        by_source.setdefault(row.source_type, []).append(row)

    for definition in SOURCE_DEFINITIONS:
        state = states.get(definition.source_type)
        source_runs = by_source.get(definition.source_type, [])
        latest = source_runs[0] if source_runs else None
        setup_status = connector_setup_status(definition.source_type)
        if setup_status in {"missing", "partial"}:
            issues.append(
                _issue(
                    category="source_missing_config",
                    severity="medium",
                    why_it_matters="Источник не может быть выполнен безопасно: часть обязательной конфигурации отсутствует.",
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Заполнить backend env vars и перезапустить backend.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "open_setup",
                    },
                )
            )
        has_success = bool(
            state and state.last_success_at
            or any(run.status == "succeeded" for run in source_runs)
        )
        if not has_success:
            issues.append(
                _issue(
                    category="source_never_synced",
                    severity="low",
                    why_it_matters="Нет ни одного успешного source run для этого источника.",
                    affected_source=definition.source_type,
                    evidence_count=len(source_runs),
                    suggested_action="Запросить test/sync и выполнить approved operator flow.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "sync",
                    },
                    related_run_id=latest.run_id if latest else None,
                    related_request_id=latest.request_id if latest else None,
                )
            )
        if latest and latest.status == "failed":
            issues.append(
                _issue(
                    category="source_failed_last_run",
                    severity="high",
                    why_it_matters="Последний source run завершился ошибкой.",
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Открыть run summary и повторить через новый request_key после fix.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "review_run",
                        "request_id": latest.request_id,
                    },
                    related_run_id=latest.run_id,
                    related_request_id=latest.request_id,
                )
            )
        failed_count = sum(1 for run in source_runs if run.status == "failed")
        if failed_count >= 2:
            issues.append(
                _issue(
                    category="source_repeated_failures",
                    severity="high",
                    why_it_matters="Источник несколько раз подряд падал в recent source runs.",
                    affected_source=definition.source_type,
                    evidence_count=failed_count,
                    suggested_action="Остановить повторные runs и исправить connector/config.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "review_failures",
                    },
                    related_run_id=latest.run_id if latest else None,
                    related_request_id=latest.request_id if latest else None,
                )
            )
        if state and state.paused and not state.last_success_at:
            issues.append(
                _issue(
                    category="source_paused_with_stale_data",
                    severity="medium",
                    why_it_matters="Источник paused, а успешного sync ещё не было или он устарел.",
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Resume source и запустить approved sync, если данные нужны.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "resume",
                    },
                    related_run_id=state.latest_run_id,
                )
            )
        open_backfills = [
            run
            for run in source_runs
            if run.action_type == "backfill" and run.status in _OPEN_REQUEST_STATUSES
        ]
        for run in open_backfills[:3]:
            issues.append(
                _issue(
                    category="backfill_requested_not_completed",
                    severity="low",
                    why_it_matters="Backfill requested, но ещё не завершён approved operator flow.",
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Запустить source request orchestrator или отменить request.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "run_requests",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )

    event_rows = (
        await session.execute(
            select(SourceEvent.source_system, func.count(SourceEvent.id)).group_by(
                SourceEvent.source_system
            )
        )
    ).all()
    normalized_rows = (
        await session.execute(
            select(
                NormalizedActivityItemRecord.source,
                func.count(NormalizedActivityItemRecord.id),
            ).group_by(NormalizedActivityItemRecord.source)
        )
    ).all()
    normalized_by_source = {str(source): int(count or 0) for source, count in normalized_rows}
    for source, count in event_rows:
        normalized_count = normalized_by_source.get(str(source), 0)
        gap = int(count or 0) - normalized_count
        if gap > 0:
            issues.append(
                _issue(
                    category="source_events_not_normalized",
                    severity="medium",
                    why_it_matters="Есть source_events, которые ещё не представлены normalized activity items.",
                    affected_source=str(source),
                    evidence_count=gap,
                    suggested_action="Запустить normalization/recheck approved flow.",
                    cta={
                        "target": "evidence_explorer",
                        "source_type": str(source),
                        "action": "view_events",
                    },
                )
            )

    counts = Counter(issue["category"] for issue in issues)
    severity = Counter(issue["severity"] for issue in issues)
    return {
        "generated_at": safe_now.isoformat(),
        "issues": issues,
        "counts": {
            "total": len(issues),
            "by_category": dict(counts),
            "by_severity": dict(severity),
        },
        "links": {
            "graph_gardener": "/v1/inbox",
            "action_center": "/v1/founder/action-center",
            "inbox": "/v1/inbox",
            "source_control": "/v1/founder/sources",
            "evidence_explorer": "/v1/source-events",
        },
    }
