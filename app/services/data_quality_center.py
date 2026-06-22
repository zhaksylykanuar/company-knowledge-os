"""Data Quality Center read model.

Every item is derived from stored evidence/read-model rows. There is no
invented score: issues are grouped by explicit, explainable signals.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentProposal, AgentRunLog, DataAvailability
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord, EntitySourceAccount
from app.db.models import AuditLog, IngestedEvent
from app.core.config import settings
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services import connector_scope
from app.services.source_connectors import REAL_CLIENT_SOURCES
from app.services.source_control import SOURCE_DEFINITIONS, connector_setup_status

_AVAILABILITY_GAP_STATUSES = {"no_data", "insufficient", "stale"}
_OPEN_REQUEST_STATUSES = {"requested", "accepted", "running"}


def _run_result(row: SourceRunRequest) -> dict[str, Any]:
    return row.result_summary if isinstance(row.result_summary, dict) else {}


def _run_ingestion(row: SourceRunRequest) -> dict[str, Any]:
    result = _run_result(row)
    summary = result.get("sanitized_summary")
    if not isinstance(summary, dict):
        return {}
    ingestion = summary.get("ingestion")
    return ingestion if isinstance(ingestion, dict) else {}


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
    related_source_event_id: str | None = None,
    related_normalized_event_id: str | None = None,
    related_graph_node: str | None = None,
    related_graph_edge: str | None = None,
    related_finding_id: str | None = None,
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
        "related_source_event_id": related_source_event_id,
        "related_normalized_event_id": related_normalized_event_id,
        "related_graph_node": related_graph_node,
        "related_graph_edge": related_graph_edge,
        "related_finding_id": related_finding_id,
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
        if (
            definition.source_type in REAL_CLIENT_SOURCES
            and setup_status == "ready"
            and not bool(getattr(settings, "enable_real_connectors", False))
        ):
            issues.append(
                _issue(
                    category="connector_real_execution_disabled",
                    severity="low",
                    why_it_matters=(
                        "Источник настроен, но real connector execution выключен: "
                        "test/sync будут безопасно skip, новые данные не придут."
                    ),
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action=(
                        "Включить FOUNDEROS_ENABLE_REAL_CONNECTORS=true и перезапустить "
                        "backend, если нужны реальные read-only данные."
                    ),
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "enable_real_connectors",
                    },
                )
            )
        real_capable = definition.source_type in REAL_CLIENT_SOURCES
        real_enabled = bool(getattr(settings, "enable_real_connectors", False))
        has_success = bool(state and state.last_success_at)
        scope_required = connector_scope.scope_required(definition.source_type)
        scope_configured = connector_scope.scope_configured(definition.source_type)
        if (
            real_capable
            and real_enabled
            and setup_status == "ready"
            and scope_required
            and not scope_configured
        ):
            issues.append(
                _issue(
                    category="connector_real_enabled_missing_scope",
                    severity="medium",
                    why_it_matters=(
                        "Real connectors включены и источник настроен, но scope не "
                        "задан: sync/backfill заблокированы, чтобы не прочитать весь org."
                    ),
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action=(
                        "Добавить " + ", ".join(
                            connector_scope.scope_field_names(definition.source_type)
                        )
                        + " и перезапустить backend."
                    ),
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "add_connector_scope",
                    },
                )
            )
        if scope_required and scope_configured and not has_success:
            issues.append(
                _issue(
                    category="connector_scope_configured_never_tested",
                    severity="low",
                    why_it_matters=(
                        "Scope задан, но успешного test/sync ещё не было."
                    ),
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Запустить Test connection, затем sync.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "test",
                    },
                )
            )
        if scope_required and connector_scope.scope_too_broad(definition.source_type):
            issues.append(
                _issue(
                    category="connector_scope_too_broad",
                    severity="medium",
                    why_it_matters=(
                        "Scope выглядит как wildcard/all — есть риск прочитать "
                        "слишком много. Сузьте до конкретных проектов/репозиториев."
                    ),
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Сузить scope до явного списка.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "narrow_connector_scope",
                    },
                )
            )
        for run in source_runs:
            result = run.result_summary if isinstance(run.result_summary, dict) else {}
            if run.status == "blocked" and result.get("blocked_reason") == "missing_scope":
                issues.append(
                    _issue(
                        category="connector_sync_blocked_missing_scope",
                        severity="medium",
                        why_it_matters=(
                            "Последний sync/backfill заблокирован: scope отсутствует."
                        ),
                        affected_source=definition.source_type,
                        evidence_count=1,
                        suggested_action="Добавить scope, затем повторить sync.",
                        cta={
                            "target": "sources",
                            "source_type": definition.source_type,
                            "action": "add_connector_scope",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
                break
        for run in source_runs:
            if run.action_type != "backfill":
                continue
            inp = (run.input_snapshot or {}).get("input") or {}
            if not inp.get("since") and not inp.get("limit"):
                issues.append(
                    _issue(
                        category="connector_backfill_limit_required",
                        severity="low",
                        why_it_matters=(
                            "Backfill без явной даты/лимита — добавь since/limit, "
                            "чтобы не читать слишком много истории."
                        ),
                        affected_source=definition.source_type,
                        evidence_count=1,
                        suggested_action="Указать since или limit для backfill.",
                        cta={
                            "target": "sources",
                            "source_type": definition.source_type,
                            "action": "backfill",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
                break
        test_ok = any(
            run.action_type == "test" and run.status == "succeeded"
            for run in source_runs
        )
        sync_runs = [run for run in source_runs if run.action_type == "sync"]
        sync_ok = bool(state and state.last_sync_at) or any(
            run.status == "succeeded" for run in sync_runs
        )
        if real_capable and real_enabled and setup_status == "ready" and not has_success:
            issues.append(
                _issue(
                    category="connector_real_enabled_never_tested",
                    severity="medium",
                    why_it_matters=(
                        "Real connectors включены и источник настроен, но успешного "
                        "test/sync ещё не было — данные не поступают."
                    ),
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Запустить Test connection, затем operator script.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "test",
                    },
                )
            )
        if test_ok and not sync_ok:
            issues.append(
                _issue(
                    category="connector_tested_not_synced",
                    severity="low",
                    why_it_matters=(
                        "Test connection прошёл, но preview sync ещё не выполнялся — "
                        "сначала проверьте scope/limits без записи events."
                    ),
                    affected_source=definition.source_type,
                    evidence_count=1,
                    suggested_action="Запустить Preview sync, затем operator script.",
                    cta={
                        "target": "sources",
                        "source_type": definition.source_type,
                        "action": "preview_sync",
                    },
                )
            )
        for run in sync_runs:
            if run.status != "succeeded":
                continue
            ingestion = _run_ingestion(run)
            if int(ingestion.get("events_ingested") or 0) == 0:
                issues.append(
                    _issue(
                        category="connector_synced_without_events",
                        severity="low",
                        why_it_matters=(
                            "Sync завершился успешно, но не принёс ни одного события — "
                            "проверь scope источника или сделай backfill."
                        ),
                        affected_source=definition.source_type,
                        evidence_count=1,
                        suggested_action="Проверить source scope или запустить Backfill.",
                        cta={
                            "target": "sources",
                            "source_type": definition.source_type,
                            "action": "backfill",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
            break
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

    for run in recent_requests:
        result = _run_result(run)
        ingestion = _run_ingestion(run)
        receipt = result.get("receipt") if isinstance(result, dict) else {}
        is_terminal = run.status not in _OPEN_REQUEST_STATUSES
        if is_terminal and not isinstance(receipt, dict):
            issues.append(
                _issue(
                    category="source_run_no_receipt",
                    severity="medium",
                    why_it_matters="A completed source run has no formal receipt.",
                    affected_source=run.source_type,
                    evidence_count=1,
                    suggested_action="Open the source run detail and rerun through Stage 18 orchestrator if needed.",
                    cta={
                        "target": "sources",
                        "source_type": run.source_type,
                        "action": "review_run",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )
            receipt = {}
        if isinstance(receipt, dict) and receipt:
            receipt_errors = receipt.get("errors_sanitized")
            if isinstance(receipt_errors, list) and receipt_errors:
                issues.append(
                    _issue(
                        category="receipt_has_errors",
                        severity="high",
                        why_it_matters="Connector run receipt contains sanitized errors.",
                        affected_source=run.source_type,
                        evidence_count=len(receipt_errors),
                        suggested_action="Inspect the run receipt before retrying.",
                        cta={
                            "target": "sources",
                            "source_type": run.source_type,
                            "action": "inspect_run_receipt",
                            "request_id": run.request_id,
                            "receipt_id": receipt.get("receipt_id"),
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
            if receipt.get("stopped_reason") == "rate_limited":
                issues.append(
                    _issue(
                        category="receipt_rate_limited",
                        severity="medium",
                        why_it_matters="Connector stopped because the provider rate limit was reached.",
                        affected_source=run.source_type,
                        evidence_count=1,
                        suggested_action="Retry after the provider window or lower the sync limit.",
                        cta={
                            "target": "sources",
                            "source_type": run.source_type,
                            "action": "lower_sync_limit",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
            if run.status == "partial_succeeded":
                issues.append(
                    _issue(
                        category="receipt_partial_success",
                        severity="medium",
                        why_it_matters="Connector run partially succeeded; inspect skipped/errors before relying on it.",
                        affected_source=run.source_type,
                        evidence_count=1,
                        suggested_action="Open receipt and retry safely if needed.",
                        cta={
                            "target": "sources",
                            "source_type": run.source_type,
                            "action": "retry_failed_run",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
            if run.action_type == "sync" and run.status in {"succeeded", "partial_succeeded"}:
                if receipt.get("output_watermark") and not receipt.get("watermark_updated"):
                    issues.append(
                        _issue(
                            category="watermark_not_updated_after_success",
                            severity="high",
                            why_it_matters="A successful sync produced an output watermark but did not advance the source watermark.",
                            affected_source=run.source_type,
                            evidence_count=1,
                            suggested_action="Inspect watermark receipt before next sync.",
                            cta={
                                "target": "sources",
                                "source_type": run.source_type,
                                "action": "investigate_watermark_issue",
                                "request_id": run.request_id,
                            },
                            related_run_id=run.run_id,
                            related_request_id=run.request_id,
                        )
                    )
            if run.status in {"failed", "blocked", "skipped"} and receipt.get("watermark_updated"):
                issues.append(
                    _issue(
                        category="watermark_updated_after_failed_run",
                        severity="high",
                        why_it_matters="A failed/blocked/skipped run appears to have advanced the watermark.",
                        affected_source=run.source_type,
                        evidence_count=1,
                        suggested_action="Investigate watermark safety before the next connector run.",
                        cta={
                            "target": "sources",
                            "source_type": run.source_type,
                            "action": "investigate_watermark_issue",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
            if run.status in {"failed", "blocked", "skipped", "partial_succeeded"}:
                issues.append(
                    _issue(
                        category="retry_available",
                        severity="low",
                        why_it_matters="This run can be retried safely through a new request.",
                        affected_source=run.source_type,
                        evidence_count=1,
                        suggested_action="Use retry safely after fixing the receipt reason.",
                        cta={
                            "target": "sources",
                            "source_type": run.source_type,
                            "action": "retry_failed_run",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
            if run.action_type == "preview_sync":
                issues.append(
                    _issue(
                        category="preview_has_not_been_synced",
                        severity="low",
                        why_it_matters="Preview read did not write source_events or advance watermark.",
                        affected_source=run.source_type,
                        evidence_count=int(receipt.get("events_seen") or 0),
                        suggested_action="Run sync after reviewing preview scope and limits.",
                        cta={
                            "target": "sources",
                            "source_type": run.source_type,
                            "action": "run_sync_after_preview",
                            "request_id": run.request_id,
                        },
                        related_run_id=run.run_id,
                        related_request_id=run.request_id,
                    )
                )
        warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        if warnings:
            issues.append(
                _issue(
                    category="connector_sanitized_warning",
                    severity="low",
                    why_it_matters="Connector returned sanitized warnings that may need operator review.",
                    affected_source=run.source_type,
                    evidence_count=len(warnings),
                    suggested_action="Open source run detail and inspect warnings.",
                    cta={
                        "target": "sources",
                        "source_type": run.source_type,
                        "action": "review_run",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )
        normalization_errors = int(ingestion.get("normalization_errors") or 0)
        if normalization_errors:
            issues.append(
                _issue(
                    category="normalization_failed",
                    severity="high",
                    why_it_matters="Some ingested source events could not be normalized into activity items.",
                    affected_source=run.source_type,
                    evidence_count=normalization_errors,
                    suggested_action="Open run errors and fix unsupported event mapping or malformed sanitized payload.",
                    cta={
                        "target": "sources",
                        "source_type": run.source_type,
                        "action": "review_run",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )
        duplicates = int(ingestion.get("duplicates_skipped") or 0)
        if duplicates:
            issues.append(
                _issue(
                    category="duplicate_source_events_skipped",
                    severity="low",
                    why_it_matters="The ingestion layer skipped duplicate source events idempotently.",
                    affected_source=run.source_type,
                    evidence_count=duplicates,
                    suggested_action="No action required unless duplicates are unexpectedly high.",
                    cta={
                        "target": "sources",
                        "source_type": run.source_type,
                        "action": "review_run",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )
        redactions = int(ingestion.get("payload_redactions") or 0)
        if redactions:
            issues.append(
                _issue(
                    category="event_payload_redacted",
                    severity="low",
                    why_it_matters="Sensitive-looking connector payload fields were redacted before persistence.",
                    affected_source=run.source_type,
                    evidence_count=redactions,
                    suggested_action="Review connector mapping and keep only sanitized fields.",
                    cta={
                        "target": "sources",
                        "source_type": run.source_type,
                        "action": "review_run",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )
        if run.action_type == "backfill" and (
            int(ingestion.get("failed_events") or 0) or normalization_errors
        ):
            issues.append(
                _issue(
                    category="backfill_completed_with_errors",
                    severity="medium",
                    why_it_matters="Backfill completed with ingestion or normalization errors.",
                    affected_source=run.source_type,
                    evidence_count=int(ingestion.get("failed_events") or 0)
                    + normalization_errors,
                    suggested_action="Review failed event summaries before retrying with a new request_key.",
                    cta={
                        "target": "sources",
                        "source_type": run.source_type,
                        "action": "review_run",
                        "request_id": run.request_id,
                    },
                    related_run_id=run.run_id,
                    related_request_id=run.request_id,
                )
            )

    failed_normalizations = (
        await session.execute(
            select(IngestedEvent)
            .where(IngestedEvent.status == "normalization_failed")
            .order_by(IngestedEvent.created_at.desc())
            .limit(20)
        )
    ).scalars()
    for row in failed_normalizations:
        issues.append(
            _issue(
                category="normalization_failed",
                severity="high",
                why_it_matters="An ingested event is marked normalization_failed.",
                affected_source=row.source_system,
                affected_entity=row.source_object_id,
                evidence_count=1,
                suggested_action="Open source event and fix the mapping before rerun.",
                cta={
                    "target": "evidence_explorer",
                    "source_type": row.source_system,
                    "status": "normalization_failed",
                },
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

    recent_normalized = (
        await session.execute(
            select(NormalizedActivityItemRecord)
            .order_by(NormalizedActivityItemRecord.created_at.desc())
            .limit(50)
        )
    ).scalars()
    for row in recent_normalized:
        marker = f"%{row.activity_item_id}%"
        linked_nodes = await session.scalar(
            select(func.count(EntityRecord.id)).where(
                cast(EntityRecord.attrs, Text).like(marker)
            )
        )
        linked_edges = await session.scalar(
            select(func.count(EntityLinkRecord.id)).where(
                cast(EntityLinkRecord.evidence_refs, Text).like(marker)
            )
        )
        if not int(linked_nodes or 0) and not int(linked_edges or 0):
            issues.append(
                _issue(
                    category="normalized_event_not_lifted_to_graph",
                    severity="medium",
                    why_it_matters="Normalized evidence exists but has not been lifted into graph nodes or evidence-backed links.",
                    affected_source=row.source,
                    affected_entity=row.source_object_id,
                    evidence_count=1 if row.source_event_id else 0,
                    suggested_action="Run the approved evidence pipeline and review graph lift errors if it remains unlinked.",
                    cta={
                        "target": "sources",
                        "source_type": row.source,
                        "action": "run_evidence_pipeline",
                    },
                    related_run_id=row.run_id,
                    related_source_event_id=row.source_event_id,
                    related_normalized_event_id=row.activity_item_id,
                )
            )

    pipeline_nodes = (
        await session.execute(
            select(EntityRecord)
            .where(EntityRecord.created_by_run_id.like("evidence_pipeline_%"))
            .order_by(EntityRecord.updated_at.desc())
            .limit(30)
        )
    ).scalars()
    for row in pipeline_nodes:
        attrs = row.attrs if isinstance(row.attrs, dict) else {}
        if not attrs.get("source_refs"):
            issues.append(
                _issue(
                    category="graph_node_without_source_refs",
                    severity="high",
                    why_it_matters="A graph node created by evidence pipeline has no source_refs, so its provenance cannot be audited.",
                    affected_entity=row.entity_id,
                    evidence_count=0,
                    suggested_action="Rebuild the node from normalized evidence or quarantine it until provenance is restored.",
                    cta={
                        "target": "knowledge_tree",
                        "action": "review_node",
                        "entity_id": row.entity_id,
                    },
                    related_run_id=row.created_by_run_id,
                    related_graph_node=row.entity_id,
                )
            )

    graph_edges_without_evidence = (
        await session.execute(
            select(EntityLinkRecord)
            .where(
                or_(
                    EntityLinkRecord.evidence_refs.is_(None),
                    func.json_array_length(EntityLinkRecord.evidence_refs) == 0,
                )
            )
            .order_by(EntityLinkRecord.created_at.desc())
            .limit(20)
        )
    ).scalars()
    for row in graph_edges_without_evidence:
        issues.append(
            _issue(
                category="graph_edge_without_evidence",
                severity="high",
                why_it_matters="Graph relation has no evidence_refs and should not be treated as an asserted relationship.",
                affected_entity=f"{row.from_entity_id}->{row.to_entity_id}",
                evidence_count=0,
                confidence=row.confidence,
                suggested_action="Remove or rebuild this edge through an approved evidence-backed flow.",
                cta={
                    "target": "knowledge_tree",
                    "action": "review_link",
                    "link_id": row.link_id,
                },
                related_run_id=row.created_by_run_id,
                related_graph_edge=row.link_id,
            )
        )

    pending_graph_proposals = (
        await session.execute(
            select(AgentProposal)
            .where(AgentProposal.status == "pending")
            .where(
                AgentProposal.kind.in_(
                    ("entity_merge_proposal", "low_confidence_relation")
                )
            )
            .order_by(AgentProposal.created_at.desc())
            .limit(30)
        )
    ).scalars()
    for row in pending_graph_proposals:
        issues.append(
            _issue(
                category="weak_identity_match_waiting_approval"
                if row.kind == "entity_merge_proposal"
                else "low_confidence_graph_relationship",
                severity="medium",
                why_it_matters="Evidence suggests a graph change, but confidence is too low for automatic assertion.",
                affected_entity=str((row.payload or {}).get("entity_id") or row.proposal_id),
                evidence_count=len(row.evidence_refs or []),
                confidence=row.confidence,
                suggested_action="Approve, reject, or keep waiting for stronger evidence in Inbox.",
                cta={
                    "target": "inbox",
                    "action": "review_proposal",
                    "proposal_id": row.proposal_id,
                },
                related_run_id=row.run_id,
            )
        )

    pipeline_findings = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.last_run_id.like("evidence_pipeline_%"))
            .order_by(SecondOpinionFinding.updated_at.desc())
            .limit(30)
        )
    ).scalars()
    for row in pipeline_findings:
        refs = [ref for ref in (row.evidence_refs or []) if isinstance(ref, dict)]
        has_full_lineage = any(
            ref.get("source_event_id") and ref.get("normalized_event_id")
            for ref in refs
        )
        if not has_full_lineage:
            issues.append(
                _issue(
                    category="finding_generated_without_full_lineage",
                    severity="high",
                    why_it_matters="A pipeline finding is missing source_event_id or normalized_event_id provenance.",
                    affected_entity=row.entity_id,
                    evidence_count=len(refs),
                    confidence=row.confidence,
                    suggested_action="Regenerate the finding from normalized evidence before showing it as an auditable conclusion.",
                    cta={
                        "target": "second_opinion",
                        "action": "review_finding",
                        "finding_key": row.finding_key,
                    },
                    related_run_id=row.last_run_id,
                    related_finding_id=row.finding_key,
                )
            )

    graph_lift_errors = (
        await session.execute(
            select(AgentRunLog)
            .where(AgentRunLog.agent == "evidence_pipeline")
            .where(AgentRunLog.errors > 0)
            .order_by(AgentRunLog.created_at.desc())
            .limit(20)
        )
    ).scalars()
    for row in graph_lift_errors:
        issues.append(
            _issue(
                category="graph_lift_error",
                severity="high",
                why_it_matters="Evidence pipeline reported graph lift errors; some normalized evidence may not reach graph/findings.",
                affected_source="evidence_pipeline",
                evidence_count=row.errors,
                suggested_action="Open the pipeline run summary and fix unsupported normalized event mapping.",
                cta={"target": "agent_runs", "action": "view_run", "run_id": row.run_id},
                related_run_id=row.run_id,
            )
        )

    # Obsidian vault stale after new graph updates.
    latest_graph_update = await session.scalar(select(func.max(EntityRecord.updated_at)))
    latest_obsidian_sync = await session.scalar(
        select(func.max(AuditLog.created_at)).where(
            AuditLog.event_type == "obsidian_vault_sync"
        )
    )
    if latest_graph_update and (
        latest_obsidian_sync is None or latest_graph_update > latest_obsidian_sync
    ):
        issues.append(
            _issue(
                category="obsidian_vault_stale",
                severity="low",
                why_it_matters=(
                    "Граф обновился после последнего Obsidian sync — vault может "
                    "не отражать свежие узлы/связи."
                ),
                affected_source="obsidian",
                evidence_count=1,
                suggested_action=(
                    "Пересинхронизировать Obsidian vault через sync_obsidian_vault.py."
                ),
                cta={"target": "knowledge_tree", "action": "sync_obsidian"},
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
