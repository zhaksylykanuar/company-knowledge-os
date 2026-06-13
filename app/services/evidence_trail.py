"""Evidence drill-down: the verifiable chain behind every finding.

source event -> normalized event -> graph node/edge -> finding ->
inbox decision. Each evidence item is resolved back to the stored
events (with raw snapshot refs) so the founder can audit why the AI
concluded what it concluded.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_control_models import SourceRunRequest
from app.services.confidence import explain_confidence
from app.services.inbox_audit import list_inbox_actions
from app.services.second_opinion import SUGGESTED_ACTIONS, _finding_read_model

# Why each conflict type means what it means — shown verbatim in the UI.
REASONING = {
    "execution_mismatch": (
        "Правило: задача In Progress без коммитов и PR за 7 дней, либо код "
        "без Jira-связи — заявленное состояние работы расходится с "
        "наблюдаемой активностью в коде."
    ),
    "stale_claim": (
        "Правило: открытая задача без движения больше 14 дней, либо Jira "
        "открыта при уже смерженном PR — заявление устарело относительно "
        "наблюдаемых событий."
    ),
    "ownership_gap": "Правило: открытая работа без назначенного ответственного.",
    "delivery_risk": (
        "Правило: просроченный срок или застрявшее ревью — наблюдаемые "
        "даты противоречат заявленным обязательствам."
    ),
    "communication_silence": (
        "Правило: входящий тред ждёт ответа дольше порога, либо контакт "
        "молчит после нашего сообщения — диалог фактически остановлен."
    ),
    "validation_gap": (
        "Правило: гипотеза заявлена проверенной, но в базе знаний нет "
        "подтверждающего evidence."
    ),
    "evidence_contradiction": (
        "Правило: заявлению противоречит сохранённое evidence "
        "(риски или факты из источников)."
    ),
    "focus_drift": (
        "Правило: заявленный фокус недели не совпадает с фактическим "
        "распределением активности команды за 7 дней."
    ),
}


def _source_ids_from_evidence(evidence_refs: list[Any]) -> list[str]:
    ids: list[str] = []
    for ref in evidence_refs or []:
        if not isinstance(ref, dict):
            continue
        for key in ("source_id", "issue_key", "pr_id", "thread_key", "source_object_id"):
            value = ref.get(key)
            if isinstance(value, str) and value and value not in ids:
                ids.append(value)
    return ids


async def _events_for_source_id(
    session: AsyncSession, source_id: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SourceEvent)
            .where(SourceEvent.source_object_id.like(f"%{source_id}%"))
            .order_by(SourceEvent.id.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "source_event_id": row.source_event_id,
            "source_system": row.source_system,
            "event_type": row.event_type,
            "title": row.title,
            "received_at": row.created_at.isoformat() if row.created_at else None,
            "raw_object_ref": row.raw_object_ref,
            "created_by_run_id": row.created_by_run_id,
        }
        for row in rows
    ]


async def _event_by_id(session: AsyncSession, event_id: str | None) -> dict[str, Any] | None:
    if not event_id:
        return None
    row = await session.scalar(
        select(SourceEvent).where(SourceEvent.source_event_id == event_id)
    )
    if row is None:
        return None
    return {
        "source_event_id": row.source_event_id,
        "source_system": row.source_system,
        "source_object_type": row.source_object_type,
        "source_object_id": row.source_object_id,
        "event_type": row.event_type,
        "title": row.title,
        "received_at": row.created_at.isoformat() if row.created_at else None,
        "raw_object_ref": row.raw_object_ref,
        "created_by_run_id": row.created_by_run_id,
    }


async def _normalized_for_source_id(
    session: AsyncSession, source_id: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(NormalizedActivityItemRecord)
            .where(
                NormalizedActivityItemRecord.source_object_id.like(f"%{source_id}%")
            )
            .order_by(NormalizedActivityItemRecord.id.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "activity_item_id": row.activity_item_id,
            "source": row.source,
            "activity_type": row.activity_type,
            "title": row.title,
            "occurred_at": (
                row.activity_created_at.isoformat()
                if row.activity_created_at
                else (row.created_at.isoformat() if row.created_at else None)
            ),
            "run_id": row.run_id,
        }
        for row in rows
    ]


async def _normalized_by_id(
    session: AsyncSession, normalized_id: str | None
) -> dict[str, Any] | None:
    if not normalized_id:
        return None
    row = await session.scalar(
        select(NormalizedActivityItemRecord).where(
            NormalizedActivityItemRecord.activity_item_id == normalized_id
        )
    )
    if row is None:
        return None
    return {
        "activity_item_id": row.activity_item_id,
        "source": row.source,
        "source_object_id": row.source_object_id,
        "source_event_id": row.source_event_id,
        "activity_type": row.activity_type,
        "title": row.title,
        "occurred_at": (
            row.activity_created_at.isoformat()
            if row.activity_created_at
            else (row.created_at.isoformat() if row.created_at else None)
        ),
        "run_id": row.run_id,
    }


async def _source_run_request(
    session: AsyncSession, run_id: str | None
) -> dict[str, Any] | None:
    if not run_id:
        return None
    row = await session.scalar(
        select(SourceRunRequest)
        .where(SourceRunRequest.run_id == run_id)
        .order_by(SourceRunRequest.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    return {
        "request_id": row.request_id,
        "run_id": row.run_id,
        "correlation_id": row.correlation_id,
        "source_type": row.source_type,
        "action_type": row.action_type,
        "status": row.status,
        "connector_summary": row.result_summary,
    }


async def _graph_lineage_for_ref(
    session: AsyncSession,
    ref: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    markers = [
        str(value)
        for value in (ref.get("normalized_event_id"), ref.get("source_event_id"))
        if isinstance(value, str) and value
    ]
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for marker in markers:
        node_rows = (
            await session.execute(
                select(EntityRecord)
                .where(cast(EntityRecord.attrs, Text).like(f"%{marker}%"))
                .limit(10)
            )
        ).scalars()
        for row in node_rows:
            model = {
                "entity_id": row.entity_id,
                "entity_type": row.entity_type,
                "name": row.canonical_name,
                "created_by_run_id": row.created_by_run_id,
                "updated_by_run_id": row.updated_by_run_id,
            }
            if model not in nodes:
                nodes.append(model)
        link_rows = (
            await session.execute(
                select(EntityLinkRecord)
                .where(cast(EntityLinkRecord.evidence_refs, Text).like(f"%{marker}%"))
                .limit(10)
            )
        ).scalars()
        for row in link_rows:
            model = {
                "link_id": row.link_id,
                "from": row.from_entity_id,
                "to": row.to_entity_id,
                "relation": row.relation,
                "confidence": row.confidence,
                "created_by_run_id": row.created_by_run_id,
            }
            if model not in links:
                links.append(model)
    return {"nodes": nodes, "links": links}


async def _related_nodes(
    session: AsyncSession, finding: dict[str, Any]
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    async def add(entity_id: str | None, via: str) -> None:
        if not entity_id or entity_id in seen:
            return
        row = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == entity_id)
        )
        if row is None:
            return
        seen.add(entity_id)
        nodes.append(
            {
                "entity_id": row.entity_id,
                "entity_type": row.entity_type,
                "name": row.canonical_name,
                "via": via,
                "created_by_run_id": row.created_by_run_id,
                "updated_by_run_id": row.updated_by_run_id,
            }
        )

    await add(finding.get("entity_id"), "затронутая сущность")

    project_id = finding.get("entity_id")
    if project_id:
        links = (
            await session.execute(
                select(EntityLinkRecord)
                .where(
                    (EntityLinkRecord.to_entity_id == project_id)
                    | (EntityLinkRecord.from_entity_id == project_id)
                )
                .limit(60)
            )
        ).scalars()
        source_ids = _source_ids_from_evidence(finding.get("evidence_refs") or [])
        jira_prefixes = {sid.split("-")[0] for sid in source_ids if "-" in sid}
        for link in links:
            other = (
                link.from_entity_id
                if link.to_entity_id == project_id
                else link.to_entity_id
            )
            if other.startswith("jira:") and other.split(":", 1)[1] in jira_prefixes:
                await add(other, f"{link.relation}")
    return nodes


async def build_finding_trail(
    session: AsyncSession, *, finding_key: str
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(SecondOpinionFinding).where(
            SecondOpinionFinding.finding_key == finding_key
        )
    )
    if row is None:
        return None
    finding = _finding_read_model(row)

    evidence_chain: list[dict[str, Any]] = []
    for ref in finding.get("evidence_refs") or []:
        if not isinstance(ref, dict):
            continue
        source_ids = _source_ids_from_evidence([ref])
        events: list[dict[str, Any]] = []
        normalized: list[dict[str, Any]] = []
        exact_event = await _event_by_id(session, ref.get("source_event_id"))
        if exact_event:
            events.append(exact_event)
        exact_normalized = await _normalized_by_id(
            session, ref.get("normalized_event_id")
        )
        if exact_normalized:
            normalized.append(exact_normalized)
        for source_id in source_ids:
            events.extend(await _events_for_source_id(session, source_id))
            normalized.extend(await _normalized_for_source_id(session, source_id))
        graph_lineage = await _graph_lineage_for_ref(session, ref)
        source_runs: list[dict[str, Any]] = []
        seen_runs: set[str] = set()
        for candidate_run_id in [
            ref.get("source_run_id"),
            *[event.get("created_by_run_id") for event in events],
        ]:
            run = await _source_run_request(session, candidate_run_id)
            if not run or str(run.get("run_id")) in seen_runs:
                continue
            seen_runs.add(str(run.get("run_id")))
            source_runs.append(run)
        evidence_chain.append(
            {
                "ref": ref,
                "source_ids": source_ids,
                "source_events": events,
                "normalized_events": normalized,
                "graph_lineage": graph_lineage,
                "source_runs": source_runs,
                "confidence": finding.get("confidence"),
            }
        )

    timeline = sorted(
        (
            event
            for item in evidence_chain
            for event in item["source_events"]
            if event.get("received_at")
        ),
        key=lambda event: str(event.get("received_at")),
    )

    related_nodes = await _related_nodes(session, finding)

    # Full provenance: every distinct run that touched any link of the
    # chain source event -> normalized -> node -> finding.
    lineage_runs: list[str] = []

    def _add_run(value: Any) -> None:
        if isinstance(value, str) and value and value not in lineage_runs:
            lineage_runs.append(value)

    for item in evidence_chain:
        for event in item["source_events"]:
            _add_run(event.get("created_by_run_id"))
        for nev in item["normalized_events"]:
            _add_run(nev.get("run_id"))
        for run in item.get("source_runs", []):
            _add_run(run.get("run_id"))
    for node in related_nodes:
        _add_run(node.get("created_by_run_id"))
        _add_run(node.get("updated_by_run_id"))
    _add_run(finding.get("last_run_id"))
    graph_lineage = {
        "nodes": [
            node
            for item in evidence_chain
            for node in (item.get("graph_lineage") or {}).get("nodes", [])
        ],
        "links": [
            link
            for item in evidence_chain
            for link in (item.get("graph_lineage") or {}).get("links", [])
        ],
    }

    return {
        "finding": finding,
        "reasoning": REASONING.get(finding["finding_type"], ""),
        "suggested_action": SUGGESTED_ACTIONS.get(finding["finding_type"], ""),
        "confidence_explanation": {
            "score": finding.get("confidence"),
            "factors": finding.get("confidence_factors") or {},
            "hint": explain_confidence(
                float(finding.get("confidence") or 0.0),
                finding.get("confidence_factors") or {},
            ),
        },
        "evidence_chain": evidence_chain,
        "evidence_timeline": timeline,
        "graph_lineage": graph_lineage,
        "related_nodes": related_nodes,
        "produced_by_run": await _run_provenance(
            session, finding.get("last_run_id")
        ),
        "lineage_run_ids": lineage_runs,
        "decision_history": await list_inbox_actions(
            session, target_id=finding_key
        ),
    }


async def _run_provenance(
    session: AsyncSession, run_id: str | None
) -> dict[str, Any] | None:
    """Which agent run last created/updated this finding — closes the
    chain from finding back to the run that produced it."""

    if not run_id:
        return None
    from app.db.agent_models import AgentRunLog

    row = await session.scalar(
        select(AgentRunLog)
        .where(AgentRunLog.run_id == run_id)
        .order_by(AgentRunLog.id.desc())
        .limit(1)
    )
    if row is None:
        return {"run_id": run_id}
    return {
        "run_id": run_id,
        "agent": row.agent,
        "agent_version": row.agent_version,
        "run_started_at": (
            row.run_started_at.isoformat() if row.run_started_at else None
        ),
        "input_watermark": row.input_watermark,
    }
