"""Action Center: one ranked "what to do next" layer.

Aggregates recommendations from second-opinion findings, graph gardener
proposals, stale/ownerless/blocked tasks, sales relationship signals,
product validation gaps and data-availability problems into a single
list. Each action carries its source and the reference needed for its
CTA, which routes to the existing decision endpoints — the Action
Center never mutates anything itself. AI proposes; the human confirms.

Actions are grouped into explainable priority buckets (Critical now /
Needs decision / Waiting for evidence / Cleanup-hygiene / Later) by a
deterministic classifier over real signals — severity, confidence,
evidence count, age/blocked/ownerless/overdue flags, visibility and
action type. There is no opaque "AI priority score": every action
carries a ``group_reason`` that states exactly why it landed where it
did, so the founder can always audit the bucketing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_control_models import SourceRunRequest
from app.services.connector_diagnostics import (
    SYNC_OBSIDIAN_CMD,
    build_connector_diagnostics,
)
from app.services.data_availability import get_availability
from app.services.execution_view import build_execution_view
from app.services.inbox import build_inbox
from app.services.sales_view import build_sales_signals
from app.services.second_opinion import _finding_read_model

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# --- priority groups ----------------------------------------------------
# Stable English keys (used by the API/UI) + Russian display labels and a
# one-line description of the rule that selects the group.
GROUP_CRITICAL = "critical_now"
GROUP_DECISION = "needs_decision"
GROUP_EVIDENCE = "waiting_for_evidence"
GROUP_CLEANUP = "cleanup"
GROUP_LATER = "later"

GROUP_ORDER = (
    GROUP_CRITICAL,
    GROUP_DECISION,
    GROUP_EVIDENCE,
    GROUP_CLEANUP,
    GROUP_LATER,
)

_GROUP_LABELS: dict[str, str] = {
    GROUP_CRITICAL: "Срочно сейчас",
    GROUP_DECISION: "Нужно решение",
    GROUP_EVIDENCE: "Ждём данные / evidence",
    GROUP_CLEANUP: "Гигиена / чистка",
    GROUP_LATER: "Потом",
}

_GROUP_RULES: dict[str, str] = {
    GROUP_CRITICAL: (
        "Высокая severity и работа уже стоит (заблокировано/просрочено) "
        "или конфликт высокой важности подтверждён evidence."
    ),
    GROUP_DECISION: (
        "Ждёт решения человека: разобрать конфликт, назначить владельца, "
        "пересмотреть срок, решить по остывающему аккаунту."
    ),
    GROUP_EVIDENCE: (
        "Пока недостаточно данных: ряд пуст/устарел, нет привязанного "
        "evidence или низкая уверенность AI — сначала собрать."
    ),
    GROUP_CLEANUP: "Гигиена графа и задачи без движения — навести порядок.",
    GROUP_LATER: "Низкий приоритет, нет срочности — вернуться позже.",
}

_LOW_CONFIDENCE = 0.5
# External connectors surfaced as next-action items in the Action Center.
_CONNECTOR_ACTION_SOURCES = {"jira", "github", "gmail"}
# pipeline_state -> (action_type, severity, title)
_CONNECTOR_ACTIONS: dict[str, tuple[str, str, str]] = {
    "missing_config": ("add_env", "medium", "add missing connector env vars"),
    "missing_scope": ("add_connector_scope", "medium", "add an explicit connector scope"),
    "real_disabled": ("enable_real_connectors", "low", "enable real connectors"),
    "never_tested": ("run_test", "medium", "run a test connection"),
    "test_requested": ("run_sync", "medium", "run the operator script for the queued request"),
    "sync_requested": ("run_sync", "medium", "run the operator script for the queued request"),
    "test_failed": ("inspect_failed_run", "high", "inspect the failed connector run"),
    "sync_failed": ("inspect_failed_run", "high", "inspect the failed connector run"),
    "test_succeeded": ("run_preview_sync", "medium", "preview connector sync"),
    "synced_no_events": ("run_sync", "low", "check source scope or backfill"),
    "sync_succeeded": ("run_evidence_pipeline", "low", "process new evidence into the graph"),
    "connected": ("run_evidence_pipeline", "low", "process new evidence into the graph"),
}
# Sources whose actions are AI conclusions that require evidence; for
# these, missing/low evidence means "waiting for evidence". Execution and
# data-availability actions are concrete (a real task / a real series), so
# they are never demoted for a zero finding-evidence count.
_AI_CONCLUSION_SOURCES = {"second_opinion", "sales"}
_DECISION_ACTION_TYPES = {
    "resolve_conflict",
    "assign_owner",
    "reengage_account",
    "renegotiate_deadline",
    "approve_merge_proposal",
    "review_low_confidence_relation",
    "review_pipeline_finding",
    "inspect_failed_graph_lift",
}
_DECISION_REASONS: dict[str, str] = {
    "resolve_conflict": "конфликт ждёт решения",
    "assign_owner": "нет владельца — назначить ответственного",
    "reengage_account": "отношения остывают — решить, что делать",
    "renegotiate_deadline": "срок под угрозой — пересмотреть",
    "approve_merge_proposal": "кандидат на merge ждёт решения",
    "review_low_confidence_relation": "слабая связь графа ждёт подтверждения",
    "review_pipeline_finding": "pipeline finding требует review",
    "inspect_failed_graph_lift": "graph lift требует диагностики",
}


def _action(
    *,
    title: str,
    why_now: str,
    affected_entity: str | None,
    evidence_count: int,
    severity: str,
    confidence: float | None,
    source: str,
    action_type: str,
    cta: str,
    action_ref: dict[str, Any],
    flags: list[str] | None = None,
    visibility: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "why_now": why_now,
        "affected_entity": affected_entity,
        "evidence_count": evidence_count,
        "severity": severity,
        "confidence": confidence,
        "source": source,
        "action_type": action_type,
        "cta": cta,
        "action_ref": action_ref,
        "flags": list(flags or []),
        "visibility": visibility,
    }


def _classify(action: dict[str, Any]) -> tuple[str, str]:
    """Return (group_key, group_reason) for one action.

    First-match-wins over explainable signals. The reason names the exact
    trigger so the bucketing is always auditable — never a hidden score.
    """

    severity = str(action.get("severity") or "low")
    confidence = action.get("confidence")
    evidence = int(action.get("evidence_count") or 0)
    flags = set(action.get("flags") or [])
    source = str(action.get("source") or "")
    action_type = str(action.get("action_type") or "")

    # Connector E2E next-actions classify by their pipeline meaning.
    if source == "connector":
        if action_type in {"inspect_failed_run", "inspect_blocked_run"}:
            return GROUP_CRITICAL, "connector run failed/blocked — нужна диагностика"
        if action_type in {"inspect_run_receipt", "retry_failed_run"}:
            return GROUP_CRITICAL, "receipt показывает ошибку/partial — нужна проверка"
        if action_type in {"lower_sync_limit", "run_sync_after_preview"}:
            return GROUP_EVIDENCE, "настроить безопасный следующий connector шаг"
        if action_type == "narrow_connector_scope":
            return GROUP_DECISION, "scope слишком широкий — сузить безопасно"
        if action_type in {
            "add_env",
            "add_connector_scope",
            "enable_real_connectors",
            "run_test",
            "run_test_connection",
            "preview_sync",
            "run_sync",
            "run_sync_after_scope",
        }:
            return GROUP_EVIDENCE, "нужен setup/scope/pilot шаг, чтобы собрать данные"
        if action_type in {"run_evidence_pipeline", "sync_obsidian"}:
            return GROUP_CLEANUP, "пост-синк обработка (graph / Obsidian)"
        return GROUP_LATER, "connector follow-up"

    blocked = "blocked" in flags or action_type == "unblock_task"
    overdue = "overdue" in flags or action_type == "renegotiate_deadline"
    stale = "stale" in flags or action_type == "refresh_task"
    is_data_gap = source == "data_availability" or action_type == "refresh_data"
    is_hygiene = source == "graph_gardener" or action_type == "review_hygiene"
    is_ai_conclusion = source in _AI_CONCLUSION_SOURCES

    # 1. Critical now — high severity and either stuck or evidence-backed.
    if severity == "high" and blocked:
        return GROUP_CRITICAL, "высокая severity + работа заблокирована"
    if severity == "high" and overdue:
        return GROUP_CRITICAL, "высокая severity + срок просрочен"
    if severity == "high" and is_ai_conclusion and evidence >= 1:
        return (
            GROUP_CRITICAL,
            f"высокая severity, конфликт подтверждён evidence ({evidence})",
        )

    # 2. Data-availability gaps are a data problem before anything else.
    if is_data_gap:
        return GROUP_EVIDENCE, "ряд данных пуст или устарел — сначала собрать данные"

    # 3. AI conclusions without enough backing need evidence, not a decision.
    if is_ai_conclusion and evidence == 0:
        return GROUP_EVIDENCE, "вывод AI без привязанного evidence — собрать подтверждение"
    if (
        is_ai_conclusion
        and confidence is not None
        and float(confidence) < _LOW_CONFIDENCE
    ):
        return (
            GROUP_EVIDENCE,
            f"низкая уверенность AI ({float(confidence):.2f}) — нужна перепроверка",
        )

    # 4. Needs a human decision — but only when it carries urgency. A
    #    low-severity decision-type item is real yet not pressing, so it
    #    drops to "later" rather than crowding the decision queue.
    if action_type in _DECISION_ACTION_TYPES and severity != "low":
        reason = _DECISION_REASONS.get(action_type, "ждёт решения человека")
        if evidence >= 1:
            reason = f"{reason} ({evidence} evidence)"
        return GROUP_DECISION, reason

    # 5. Cleanup / hygiene.
    if is_hygiene:
        return GROUP_CLEANUP, "предложение по гигиене графа знаний"
    if stale:
        return GROUP_CLEANUP, "задача без движения — обновить или закрыть"

    # 6. Everything else can wait.
    bits = [f"severity {severity}"]
    if confidence is not None:
        bits.append(f"conf {float(confidence):.2f}")
    return GROUP_LATER, "низкий приоритет, нет срочности (" + ", ".join(bits) + ")"


def _grouped(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket already-sorted actions into the ordered priority groups.

    Each action is stamped with ``group`` + ``group_reason`` in place; the
    returned list preserves GROUP_ORDER and the within-group sort order.
    """

    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in GROUP_ORDER}
    for action in actions:
        group_key, reason = _classify(action)
        action["group"] = group_key
        action["group_reason"] = reason
        buckets[group_key].append(action)
    return [
        {
            "key": key,
            "label": _GROUP_LABELS[key],
            "rule": _GROUP_RULES[key],
            "actions": buckets[key],
            "count": len(buckets[key]),
        }
        for key in GROUP_ORDER
    ]


async def build_action_center(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    actions: list[dict[str, Any]] = []

    # 1. Second opinion findings (open).
    finding_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == "open")
            .where(
                (SecondOpinionFinding.snoozed_until.is_(None))
                | (SecondOpinionFinding.snoozed_until <= safe_now)
            )
            .order_by(SecondOpinionFinding.updated_at.desc(), SecondOpinionFinding.id.desc())
            .limit(60)
        )
    ).scalars()
    for row in finding_rows:
        f = _finding_read_model(row)
        actions.append(
            _action(
                title=f["summary"],
                why_now=f["observed_state"],
                affected_entity=f["entity_id"],
                evidence_count=len(f.get("evidence_refs") or []),
                severity=f["severity"],
                confidence=f["confidence"],
                source="second_opinion",
                action_type="resolve_conflict",
                cta=f.get("suggested_action") or "Разобрать конфликт",
                action_ref={"kind": "finding", "finding_key": f["finding_key"]},
                visibility=f.get("visibility_scope"),
            )
        )

    # 2. Graph gardener proposals (pending hygiene decisions).
    inbox = await build_inbox(session, limit=60)
    for proposal in inbox.get("gardener_proposals", []):
        actions.append(
            _action(
                title=proposal["title"],
                why_now=proposal.get("why") or "Гигиена графа знаний",
                affected_entity=(proposal.get("payload") or {}).get("entity_id"),
                evidence_count=len(proposal.get("evidence_refs") or []),
                severity="low",
                confidence=proposal.get("confidence"),
                source="graph_gardener",
                action_type="review_hygiene",
                cta="Решить в Inbox",
                action_ref={"kind": "proposal", "proposal_id": proposal["proposal_id"]},
            )
        )
    for proposal in inbox.get("proposals", []):
        ptype = proposal.get("proposal_type")
        if ptype in {"entity_merge_proposal", "low_confidence_relation", "finding_suggestion"}:
            action_type = {
                "entity_merge_proposal": "approve_merge_proposal",
                "low_confidence_relation": "review_low_confidence_relation",
                "finding_suggestion": "review_pipeline_finding",
            }[ptype]
            actions.append(
                _action(
                    title=proposal["title"],
                    why_now=proposal.get("why")
                    or proposal.get("confidence_hint")
                    or "Evidence pipeline filed a proposal that needs review.",
                    affected_entity=(proposal.get("payload") or {}).get("entity_id")
                    or (proposal.get("payload") or {}).get("from_entity_id"),
                    evidence_count=len(proposal.get("evidence_refs") or []),
                    severity="medium" if ptype != "finding_suggestion" else "low",
                    confidence=proposal.get("confidence"),
                    source="evidence_pipeline"
                    if ptype != "entity_merge_proposal"
                    else "entity_identity",
                    action_type=action_type,
                    cta="Решить в Inbox",
                    action_ref={
                        "kind": "proposal",
                        "proposal_id": proposal["proposal_id"],
                    },
                    flags=["low_confidence"] if ptype != "entity_merge_proposal" else [],
                )
            )

    # 3. Execution: stale / ownerless / blocked / overdue tasks.
    execution = await build_execution_view(session, now=safe_now)
    for bucket, action_type, cta, sev in (
        ("blocked_quests", "unblock_task", "Разблокировать", "high"),
        ("overdue_quests", "renegotiate_deadline", "Передоговорить срок", "high"),
        ("ownerless_quests", "assign_owner", "Назначить ответственного", "medium"),
        ("stale_quests", "refresh_task", "Обновить или закрыть", "medium"),
    ):
        for quest in execution.get(bucket, [])[:5]:
            actions.append(
                _action(
                    title=f"[{quest['issue_key']}] {quest['title'][:120]}",
                    why_now=", ".join(quest["flags"]),
                    affected_entity=quest.get("project"),
                    evidence_count=quest.get("evidence_count", 0),
                    severity=sev,
                    confidence=None,
                    source="execution",
                    action_type=action_type,
                    cta=cta,
                    action_ref={"kind": "task", "issue_key": quest["issue_key"]},
                    flags=quest.get("flags"),
                )
            )

    # 4. Sales relationship signals.
    sales = await build_sales_signals(session)
    for account in sales.get("accounts", []):
        for signal in account.get("signals", []):
            actions.append(
                _action(
                    title=signal["summary"],
                    why_now=signal["observed_state"],
                    affected_entity=account.get("client_id"),
                    evidence_count=len(signal.get("evidence_refs") or []),
                    severity=signal["severity"],
                    confidence=signal["confidence"],
                    source="sales",
                    action_type="reengage_account",
                    cta=signal.get("suggested_action") or "Написать контакту",
                    action_ref={"kind": "finding", "finding_key": signal["finding_key"]},
                    visibility=signal.get("visibility_scope"),
                )
            )

    # 5. Data availability problems (stale / no_data series).
    availability = await get_availability(session)
    for row in availability:
        if row["status"] in {"stale", "no_data"}:
            actions.append(
                _action(
                    title=f"Данные: {row['metric_key']} ({row['scope']})",
                    why_now=row["message"],
                    affected_entity=row["scope"],
                    evidence_count=row["points_count"],
                    severity="low",
                    confidence=None,
                    source="data_availability",
                    action_type="refresh_data",
                    cta="Прогнать агентов / синк",
                    action_ref={"kind": "metric", "metric_key": row["metric_key"]},
                )
            )

    # 6. Connector E2E next-actions (read-only; the CTA is a copyable command).
    diagnostics = await build_connector_diagnostics(session)
    evidence_pending = False
    for connector in diagnostics.get("connectors", []):
        source_type = connector["source_type"]
        if source_type not in _CONNECTOR_ACTION_SOURCES:
            continue
        if connector.get("scope_too_broad"):
            runbook = connector.get("runbook") or {}
            actions.append(
                _action(
                    title=f"{connector['label']}: narrow the connector scope",
                    why_now="Scope looks like a wildcard/all — narrow it to avoid a "
                    "broad read.",
                    affected_entity=source_type,
                    evidence_count=int(connector.get("events_ingested") or 0),
                    severity="medium",
                    confidence=None,
                    source="connector",
                    action_type="narrow_connector_scope",
                    cta=runbook.get("next_command") or "Open Sources / Data Control",
                    action_ref={
                        "kind": "connector",
                        "source_type": source_type,
                        "pipeline_state": connector.get("pipeline_state"),
                    },
                )
            )
        spec = _CONNECTOR_ACTIONS.get(connector.get("pipeline_state"))
        if spec is None:
            continue
        action_type, severity, title = spec
        events = int(connector.get("events_ingested") or 0)
        if action_type == "run_evidence_pipeline":
            if not events:
                continue
            evidence_pending = True
        runbook = connector.get("runbook") or {}
        actions.append(
            _action(
                title=f"{connector['label']}: {title}",
                why_now=runbook.get("next_action") or "Connector needs attention.",
                affected_entity=source_type,
                evidence_count=events,
                severity=severity,
                confidence=None,
                source="connector",
                action_type=action_type,
                cta=runbook.get("next_command") or "Open Sources / Data Control",
                action_ref={
                    "kind": "connector",
                    "source_type": source_type,
                    "pipeline_state": connector.get("pipeline_state"),
                },
            )
        )
    if evidence_pending:
        actions.append(
            _action(
                title="Sync the Obsidian vault after new graph updates",
                why_now="New evidence was lifted into the graph; refresh the vault.",
                affected_entity=None,
                evidence_count=0,
                severity="low",
                confidence=None,
                source="connector",
                action_type="sync_obsidian",
                cta=SYNC_OBSIDIAN_CMD,
                action_ref={"kind": "obsidian", "action": "sync_vault"},
            )
        )

    # 7. Connector run receipt next-actions.
    receipt_rows = (
        await session.execute(
            select(SourceRunRequest)
            .where(SourceRunRequest.run_id.is_not(None))
            .order_by(SourceRunRequest.created_at.desc(), SourceRunRequest.id.desc())
            .limit(40)
        )
    ).scalars()
    for row in receipt_rows:
        result = row.result_summary if isinstance(row.result_summary, dict) else {}
        receipt = result.get("receipt") if isinstance(result, dict) else {}
        if not isinstance(receipt, dict) or not receipt:
            continue
        action_type = None
        title = None
        why = None
        severity = "low"
        if row.status in {"failed", "blocked"}:
            action_type = "inspect_run_receipt"
            title = f"{row.source_type}: inspect failed connector receipt"
            why = str(receipt.get("blocked_reason") or "run failed")
            severity = "high"
        elif row.status == "partial_succeeded":
            action_type = "retry_failed_run"
            title = f"{row.source_type}: retry partial connector run"
            why = "partial success in connector receipt"
            severity = "medium"
        elif receipt.get("stopped_reason") == "rate_limited":
            action_type = "lower_sync_limit"
            title = f"{row.source_type}: narrow sync after rate limit"
            why = "provider rate limit reached"
            severity = "medium"
        elif row.action_type == "preview_sync":
            action_type = "run_sync_after_preview"
            title = f"{row.source_type}: run sync after preview"
            why = "preview wrote no source_events and watermark stayed unchanged"
            severity = "low"
        if action_type is None:
            continue
        actions.append(
            _action(
                title=title or "Inspect connector receipt",
                why_now=why or "receipt requires review",
                affected_entity=row.source_type,
                evidence_count=int(receipt.get("events_seen") or 0),
                severity=severity,
                confidence=None,
                source="connector",
                action_type=action_type,
                cta="Open Sources / Data Control",
                action_ref={
                    "kind": "connector_receipt",
                    "source_type": row.source_type,
                    "request_id": row.request_id,
                    "receipt_id": receipt.get("receipt_id"),
                },
            )
        )

    actions.sort(
        key=lambda a: (
            _SEVERITY_RANK.get(a["severity"], 3),
            -(a["evidence_count"] or 0),
        )
    )

    limited = actions[:limit]
    groups = _grouped(limited)

    by_source: dict[str, int] = {}
    for a in actions:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1
    by_group = {group["key"]: group["count"] for group in groups}

    return {
        "generated_at": safe_now.isoformat(),
        "actions": limited,
        "groups": groups,
        "counts": {
            "total": len(actions),
            "by_source": by_source,
            "by_group": by_group,
        },
    }
