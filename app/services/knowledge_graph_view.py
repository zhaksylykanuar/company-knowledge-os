"""Obsidian-like knowledge graph and note read models.

This is a read-model layer over the existing graph/source/finding/proposal
tables. It does not introduce a second graph store and never writes files or
calls external providers.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentProposal
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_control_models import SourceRunRequest
from app.services.browser_config import sanitize_for_logs
from app.services.confidence import explain_confidence
from app.services.obsidian_exporter import sanitize_obsidian_filename
from app.services.visibility import (
    SCOPE_FOUNDER,
    SCOPE_INVESTOR,
    redaction_manifest,
)

DISPUTED_CONFIDENCE_THRESHOLD = 0.7
FRESHNESS_HALF_LIFE_DAYS = 7.0
MAX_GRAPH_LIMIT = 300
DEFAULT_GRAPH_LIMIT = 120
VIRTUAL_SOURCE_LIMIT = 40
VIRTUAL_FINDING_LIMIT = 40
VIRTUAL_PROPOSAL_LIMIT = 40

ENTITY_TYPE_MAP = {
    "repository": "repo",
    "client": "account",
    "jira_project": "project",
}

NODE_TYPE_LABELS = {
    "project": "Project",
    "person": "Person",
    "task": "Task",
    "repo": "Repo",
    "issue": "Issue",
    "pull_request": "Pull request",
    "commit": "Commit",
    "meeting": "Meeting",
    "decision": "Decision",
    "action_item": "Action item",
    "risk": "Risk",
    "blocker": "Blocker",
    "account": "Account",
    "contact": "Contact",
    "email_thread": "Email thread",
    "hypothesis": "Hypothesis",
    "declaration": "Declaration",
    "feature": "Feature",
    "product_area": "Product area",
    "share_pack": "Share pack",
    "source_event": "Source event",
    "normalized_event": "Normalized event",
    "finding": "Finding",
    "proposal": "Proposal",
    "knowledge_note": "Knowledge note",
}

RELATION_LABELS = {
    "works_on": "Works on",
    "owns": "Owns",
    "assigned_to": "Assigned to",
    "blocks": "Blocks",
    "depends_on": "Depends on",
    "mentions": "Mentions",
    "decided_in": "Decided in",
    "next_step_of": "Next step of",
    "affects": "Affects",
    "evidence_for": "Evidence for",
    "contradicts": "Contradicts",
    "supports": "Supports",
    "validates": "Validates",
    "invalidates": "Invalidates",
    "generated_from": "Generated from",
    "linked_to_source": "Linked to source",
    "related_to": "Related to",
    "same_as_candidate": "Same as candidate",
    "belongs_to_project": "Belongs to project",
    "belongs_to_account": "Belongs to account",
    "created_by": "Created by",
    "updated_by": "Updated by",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _limit(value: int) -> int:
    return max(1, min(int(value or DEFAULT_GRAPH_LIMIT), MAX_GRAPH_LIMIT))


def _freshness(updated_at: datetime | None, now: datetime) -> float:
    if updated_at is None:
        return 0.1
    age_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
    return round(1.0 / (1.0 + age_days / FRESHNESS_HALF_LIFE_DAYS), 2)


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean(value: Any, *, max_chars: int = 500) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text[:max_chars] or None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _node_type(entity_type: str, attrs: dict[str, Any]) -> str:
    source_types = {str(item) for item in _as_list(attrs.get("source_types"))}
    role = str(attrs.get("entity_role") or "")
    if entity_type == "task" and "github" in source_types:
        if "commit" in role:
            return "commit"
        return "pull_request"
    if entity_type == "task" and "jira" in source_types:
        return "issue"
    return ENTITY_TYPE_MAP.get(entity_type, entity_type)


def _relation_type(relation: str, target_node_type: str | None = None) -> str:
    if relation == "belongs_to" and target_node_type == "project":
        return "belongs_to_project"
    if relation == "belongs_to" and target_node_type == "account":
        return "belongs_to_account"
    return relation if relation in RELATION_LABELS else "related_to"


def _tags(node_type: str, source_types: list[Any], attrs: dict[str, Any]) -> list[str]:
    tags = {node_type}
    tags.update(str(item) for item in source_types if item)
    role = attrs.get("entity_role")
    if role:
        tags.add(str(role))
    return sorted(tags)


def _redact_properties(properties: dict[str, Any], viewer_scope: str) -> dict[str, Any]:
    safe = sanitize_for_logs(dict(properties))
    if viewer_scope == SCOPE_FOUNDER:
        return safe
    for field in (
        "source_refs",
        "source_event_ids",
        "normalized_event_ids",
        "raw_object_ref",
        "source_url",
        "evidence_refs",
    ):
        safe.pop(field, None)
    if viewer_scope == SCOPE_INVESTOR:
        return {
            key: safe[key]
            for key in ("status", "summary", "evidence_count", "confidence")
            if key in safe
        }
    return safe


def _redact_title(title: str, node_type: str, viewer_scope: str) -> str:
    if viewer_scope == SCOPE_INVESTOR and node_type in {"person", "contact"}:
        return "Person"
    return title


def _knowledge_redaction_manifest(
    viewer_scope: str,
    *,
    included_sections: list[str] | None = None,
    excluded_sections: list[str] | None = None,
) -> dict[str, object]:
    manifest = redaction_manifest(
        viewer_scope,
        included_sections=included_sections,
        excluded_sections=excluded_sections,
    )
    manifest.pop("finance_visible", None)
    return manifest


def _safe_source_refs(attrs: dict[str, Any], viewer_scope: str) -> list[dict[str, Any]]:
    if viewer_scope != SCOPE_FOUNDER:
        return []
    refs = [ref for ref in _as_list(attrs.get("source_refs")) if isinstance(ref, dict)]
    return sanitize_for_logs(refs)


async def _finding_count(session: AsyncSession, entity_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count(SecondOpinionFinding.id)).where(
                SecondOpinionFinding.entity_id == entity_id
            )
        )
        or 0
    )


async def _proposal_count(session: AsyncSession, entity_id: str) -> int:
    marker = f"%{entity_id}%"
    return int(
        await session.scalar(
            select(func.count(AgentProposal.id)).where(
                or_(
                    cast(AgentProposal.payload, Text).like(marker),
                    cast(AgentProposal.evidence_refs, Text).like(marker),
                )
            )
        )
        or 0
    )


async def _entity_node(
    session: AsyncSession,
    row: EntityRecord,
    *,
    viewer_scope: str,
    now: datetime,
) -> dict[str, Any] | None:
    attrs = _as_dict(row.attrs)
    archived = bool(attrs.get("archived"))
    node_type = _node_type(row.entity_type, attrs)
    visibility_scope = str(attrs.get("visibility_scope") or SCOPE_FOUNDER)
    source_types = [str(item) for item in _as_list(attrs.get("source_types")) if item]
    evidence_count = int(attrs.get("evidence_count") or len(_as_list(attrs.get("source_refs"))))
    confidence = float(attrs.get("confidence") or row.merge_confidence or 1.0)
    title = _clean(row.canonical_name, max_chars=255) or row.entity_id
    properties = _redact_properties(
        {
            **attrs,
            "canonical_entity_id": row.canonical_entity_id,
            "merge_status": row.merge_status,
        },
        viewer_scope,
    )
    return {
        "node_id": row.entity_id,
        "node_type": node_type,
        "title": _redact_title(title, node_type, viewer_scope),
        "summary": _clean(attrs.get("summary") or attrs.get("entity_role") or title),
        "tags": _tags(node_type, source_types, attrs),
        "properties": properties,
        "source_types": source_types if viewer_scope != SCOPE_INVESTOR else [],
        "source_refs": _safe_source_refs(attrs, viewer_scope),
        "evidence_count": evidence_count,
        "finding_count": await _finding_count(session, row.entity_id),
        "proposal_count": await _proposal_count(session, row.entity_id),
        "confidence": round(confidence, 2),
        "confidence_explanation": explain_confidence(
            confidence,
            {
                "evidence_count": evidence_count,
                "source_quality": confidence,
                "freshness": _freshness(row.updated_at or row.created_at, now),
                "cross_source_match": len(source_types) > 1,
            },
        ),
        "freshness": _freshness(row.updated_at or row.created_at, now),
        "last_observed_at": attrs.get("last_observed_at"),
        "created_by_run_id": row.created_by_run_id,
        "updated_by_run_id": row.updated_by_run_id,
        "visibility_scope": visibility_scope,
        "archived": archived,
        "canonical_entity_id": row.canonical_entity_id,
    }


def _edge_model(
    row: EntityLinkRecord,
    *,
    source_type: str | None,
    target_type: str | None,
    viewer_scope: str,
) -> dict[str, Any]:
    factors = _as_dict(row.confidence_factors)
    evidence_refs = _as_list(row.evidence_refs)
    source_event_ids = [str(item) for item in _as_list(factors.get("source_event_ids")) if item]
    normalized_event_ids = [
        str(item) for item in _as_list(factors.get("normalized_event_ids")) if item
    ]
    relation_type = _relation_type(row.relation, target_type)
    return {
        "edge_id": row.link_id,
        "source_node_id": row.from_entity_id,
        "target_node_id": row.to_entity_id,
        "from": row.from_entity_id,
        "to": row.to_entity_id,
        "relation_type": relation_type,
        "relation": relation_type,
        "confidence": round(float(row.confidence or 0.0), 2),
        "confidence_explanation": explain_confidence(
            float(row.confidence or 0.0),
            factors,
        ),
        "evidence_ids": [str(ref.get("source_event_id") or ref.get("normalized_event_id")) for ref in evidence_refs if isinstance(ref, dict)],
        "source_event_ids": source_event_ids if viewer_scope == SCOPE_FOUNDER else [],
        "normalized_event_ids": normalized_event_ids if viewer_scope != SCOPE_INVESTOR else [],
        "finding_ids": [],
        "proposal_ids": [],
        "created_by_run_id": row.created_by_run_id,
        "updated_by_run_id": factors.get("updated_by_run_id"),
        "last_observed_at": factors.get("last_observed_at"),
        "disputed": float(row.confidence or 0.0) < DISPUTED_CONFIDENCE_THRESHOLD,
        "visibility_scope": factors.get("visibility_scope") or SCOPE_FOUNDER,
        "evidence_refs": sanitize_for_logs(evidence_refs) if viewer_scope == SCOPE_FOUNDER else [],
        "source_node_type": source_type,
        "target_node_type": target_type,
    }


def _virtual_node(
    *,
    node_id: str,
    node_type: str,
    title: str,
    summary: str | None,
    source_types: list[str],
    evidence_count: int = 1,
    confidence: float = 1.0,
    created_by_run_id: str | None = None,
    updated_by_run_id: str | None = None,
    last_observed_at: str | None = None,
    properties: dict[str, Any] | None = None,
    viewer_scope: str,
) -> dict[str, Any]:
    props = _redact_properties(properties or {}, viewer_scope)
    return {
        "node_id": node_id,
        "node_type": node_type,
        "title": _redact_title(title, node_type, viewer_scope),
        "summary": summary,
        "tags": _tags(node_type, source_types, props),
        "properties": props,
        "source_types": source_types if viewer_scope != SCOPE_INVESTOR else [],
        "source_refs": [],
        "evidence_count": evidence_count,
        "finding_count": 0,
        "proposal_count": 0,
        "confidence": round(confidence, 2),
        "freshness": 0.8,
        "last_observed_at": last_observed_at,
        "created_by_run_id": created_by_run_id,
        "updated_by_run_id": updated_by_run_id,
        "visibility_scope": SCOPE_FOUNDER,
        "archived": False,
        "canonical_entity_id": None,
    }


def _virtual_edge(
    *,
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    relation_type: str,
    confidence: float,
    evidence_ids: list[str] | None = None,
    source_event_ids: list[str] | None = None,
    normalized_event_ids: list[str] | None = None,
    finding_ids: list[str] | None = None,
    proposal_ids: list[str] | None = None,
    run_id: str | None = None,
    viewer_scope: str,
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "from": source_node_id,
        "to": target_node_id,
        "relation_type": relation_type,
        "relation": relation_type,
        "confidence": round(confidence, 2),
        "evidence_ids": list(evidence_ids or []),
        "source_event_ids": list(source_event_ids or []) if viewer_scope == SCOPE_FOUNDER else [],
        "normalized_event_ids": list(normalized_event_ids or []) if viewer_scope != SCOPE_INVESTOR else [],
        "finding_ids": list(finding_ids or []),
        "proposal_ids": list(proposal_ids or []),
        "created_by_run_id": run_id,
        "updated_by_run_id": run_id,
        "last_observed_at": None,
        "disputed": confidence < DISPUTED_CONFIDENCE_THRESHOLD,
        "visibility_scope": SCOPE_FOUNDER,
        "evidence_refs": [],
    }


async def _base_entities(
    session: AsyncSession,
    *,
    include_archived: bool,
) -> list[EntityRecord]:
    rows = (
        await session.execute(
            select(EntityRecord).order_by(EntityRecord.updated_at.desc(), EntityRecord.id.desc())
        )
    ).scalars().all()
    if include_archived:
        return rows
    return [row for row in rows if not _as_dict(row.attrs).get("archived")]


async def _source_event_virtuals(
    session: AsyncSession,
    *,
    viewer_scope: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if viewer_scope == SCOPE_INVESTOR:
        return [], []
    rows = (
        await session.execute(
            select(SourceEvent)
            .order_by(SourceEvent.created_at.desc(), SourceEvent.id.desc())
            .limit(min(limit, VIRTUAL_SOURCE_LIMIT))
        )
    ).scalars().all()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row in rows:
        node_id = f"source_event:{row.source_event_id}"
        nodes.append(
            _virtual_node(
                node_id=node_id,
                node_type="source_event",
                title=row.title or row.source_object_id,
                summary=row.summary,
                source_types=[row.source_system],
                created_by_run_id=row.created_by_run_id,
                last_observed_at=row.source_event_ts.isoformat() if row.source_event_ts else None,
                properties={
                    "source_event_id": row.source_event_id,
                    "source_system": row.source_system,
                    "source_object_type": row.source_object_type,
                    "source_object_id": row.source_object_id,
                    "raw_object_ref": row.raw_object_ref,
                    "source_url": row.source_url,
                },
                viewer_scope=viewer_scope,
            )
        )
        normalized = (
            await session.execute(
                select(NormalizedActivityItemRecord)
                .where(NormalizedActivityItemRecord.source_event_id == row.source_event_id)
                .limit(5)
            )
        ).scalars().all()
        for item in normalized:
            normalized_id = f"normalized_event:{item.activity_item_id}"
            edges.append(
                _virtual_edge(
                    edge_id=f"{normalized_id}->generated_from->{node_id}",
                    source_node_id=normalized_id,
                    target_node_id=node_id,
                    relation_type="generated_from",
                    confidence=1.0,
                    evidence_ids=[row.source_event_id, item.activity_item_id],
                    source_event_ids=[row.source_event_id],
                    normalized_event_ids=[item.activity_item_id],
                    run_id=row.created_by_run_id,
                    viewer_scope=viewer_scope,
                )
            )
    return nodes, edges


async def _normalized_virtuals(
    session: AsyncSession,
    *,
    viewer_scope: str,
    limit: int,
) -> list[dict[str, Any]]:
    if viewer_scope == SCOPE_INVESTOR:
        return []
    rows = (
        await session.execute(
            select(NormalizedActivityItemRecord)
            .order_by(NormalizedActivityItemRecord.created_at.desc(), NormalizedActivityItemRecord.id.desc())
            .limit(min(limit, VIRTUAL_SOURCE_LIMIT))
        )
    ).scalars().all()
    return [
        _virtual_node(
            node_id=f"normalized_event:{row.activity_item_id}",
            node_type="normalized_event",
            title=row.title or row.source_object_id,
            summary=row.safe_summary,
            source_types=[row.source],
            created_by_run_id=row.run_id,
            last_observed_at=(
                row.activity_created_at.isoformat()
                if row.activity_created_at
                else (row.created_at.isoformat() if row.created_at else None)
            ),
            properties={
                "activity_item_id": row.activity_item_id,
                "source_event_id": row.source_event_id,
                "source_object_id": row.source_object_id,
                "activity_type": row.activity_type,
                "project": row.project,
            },
            viewer_scope=viewer_scope,
        )
        for row in rows
    ]


async def _finding_virtuals(
    session: AsyncSession,
    *,
    viewer_scope: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if viewer_scope == SCOPE_INVESTOR:
        return [], []
    rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .order_by(SecondOpinionFinding.updated_at.desc(), SecondOpinionFinding.id.desc())
            .limit(min(limit, VIRTUAL_FINDING_LIMIT))
        )
    ).scalars().all()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row in rows:
        node_id = f"finding:{row.finding_key}"
        evidence_refs = [ref for ref in _as_list(row.evidence_refs) if isinstance(ref, dict)]
        nodes.append(
            _virtual_node(
                node_id=node_id,
                node_type="finding",
                title=row.summary,
                summary=row.observed_state,
                source_types=["second_opinion"],
                evidence_count=len(evidence_refs),
                confidence=float(row.confidence or 0.0),
                created_by_run_id=row.last_run_id,
                updated_by_run_id=row.last_run_id,
                properties={
                    "finding_key": row.finding_key,
                    "finding_type": row.finding_type,
                    "severity": row.severity,
                    "status": row.status,
                    "evidence_refs": evidence_refs,
                },
                viewer_scope=viewer_scope,
            )
        )
        if row.entity_id:
            edges.append(
                _virtual_edge(
                    edge_id=f"{node_id}->evidence_for->{row.entity_id}",
                    source_node_id=node_id,
                    target_node_id=row.entity_id,
                    relation_type="evidence_for",
                    confidence=float(row.confidence or 0.0),
                    evidence_ids=[
                        str(ref.get("source_event_id") or ref.get("normalized_event_id"))
                        for ref in evidence_refs
                        if ref.get("source_event_id") or ref.get("normalized_event_id")
                    ],
                    source_event_ids=[
                        str(ref.get("source_event_id"))
                        for ref in evidence_refs
                        if ref.get("source_event_id")
                    ],
                    normalized_event_ids=[
                        str(ref.get("normalized_event_id"))
                        for ref in evidence_refs
                        if ref.get("normalized_event_id")
                    ],
                    finding_ids=[row.finding_key],
                    run_id=row.last_run_id,
                    viewer_scope=viewer_scope,
                )
            )
    return nodes, edges


async def _proposal_virtuals(
    session: AsyncSession,
    *,
    viewer_scope: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if viewer_scope == SCOPE_INVESTOR:
        return [], []
    rows = (
        await session.execute(
            select(AgentProposal)
            .where(AgentProposal.status == "pending")
            .order_by(AgentProposal.created_at.desc(), AgentProposal.id.desc())
            .limit(min(limit, VIRTUAL_PROPOSAL_LIMIT))
        )
    ).scalars().all()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row in rows:
        node_id = f"proposal:{row.proposal_id}"
        payload = _as_dict(row.payload)
        nodes.append(
            _virtual_node(
                node_id=node_id,
                node_type="proposal",
                title=row.title,
                summary=f"{row.kind} waiting for review",
                source_types=[row.agent],
                evidence_count=len(row.evidence_refs or []),
                confidence=float(row.confidence or 0.0),
                created_by_run_id=row.run_id,
                properties={
                    "proposal_id": row.proposal_id,
                    "proposal_type": row.kind,
                    "status": row.status,
                    "payload": payload,
                    "evidence_refs": row.evidence_refs,
                },
                viewer_scope=viewer_scope,
            )
        )
        target = payload.get("to_entity_id") or payload.get("entity_id") or payload.get("keep")
        if isinstance(target, str) and target:
            edges.append(
                _virtual_edge(
                    edge_id=f"{node_id}->same_as_candidate->{target}",
                    source_node_id=node_id,
                    target_node_id=target,
                    relation_type="same_as_candidate"
                    if row.kind == "entity_merge_proposal"
                    else "related_to",
                    confidence=float(row.confidence or 0.0),
                    proposal_ids=[row.proposal_id],
                    run_id=row.run_id,
                    viewer_scope=viewer_scope,
                )
            )
    return nodes, edges


def _apply_node_filters(
    nodes: list[dict[str, Any]],
    *,
    node_type: str | None,
    source_type: str | None,
    tag: str | None,
    q: str | None,
    min_confidence: float | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    needle = (q or "").casefold().strip()
    for node in nodes:
        if node_type and node["node_type"] != node_type:
            continue
        if source_type and source_type not in set(node.get("source_types") or []):
            continue
        if tag and tag not in set(node.get("tags") or []):
            continue
        if min_confidence is not None and float(node.get("confidence") or 0.0) < min_confidence:
            continue
        if needle and needle not in f"{node['node_id']} {node.get('title')} {node.get('summary')}".casefold():
            continue
        out.append(node)
    return out


def _apply_edge_filters(
    edges: list[dict[str, Any]],
    *,
    relation_type: str | None,
    min_confidence: float | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edge in edges:
        if relation_type and edge["relation_type"] != relation_type:
            continue
        if min_confidence is not None and float(edge.get("confidence") or 0.0) < min_confidence:
            continue
        out.append(edge)
    return out


def _local_graph(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    focus_node_id: str,
    depth: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge["source_node_id"]].add(edge["target_node_id"])
        adjacency[edge["target_node_id"]].add(edge["source_node_id"])
    seen = {focus_node_id}
    queue: deque[tuple[str, int]] = deque([(focus_node_id, 0)])
    max_depth = max(1, min(int(depth or 1), 3))
    while queue:
        node_id, level = queue.popleft()
        if level >= max_depth:
            continue
        for next_id in adjacency.get(node_id, set()):
            if next_id in seen:
                continue
            seen.add(next_id)
            queue.append((next_id, level + 1))
    local_nodes = [node for node in nodes if node["node_id"] in seen]
    local_edges = [
        edge
        for edge in edges
        if edge["source_node_id"] in seen and edge["target_node_id"] in seen
    ]
    return local_nodes, local_edges


def _clusters(nodes: list[dict[str, Any]], hidden_count: int) -> list[dict[str, Any]]:
    by_type = Counter(node["node_type"] for node in nodes)
    by_source: Counter[str] = Counter()
    for node in nodes:
        by_source.update(node.get("source_types") or [])
    clusters = [
        {"cluster_id": f"type:{node_type}", "label": node_type, "count": count, "kind": "node_type"}
        for node_type, count in by_type.most_common()
    ]
    clusters.extend(
        {
            "cluster_id": f"source:{source}",
            "label": source,
            "count": count,
            "kind": "source_type",
        }
        for source, count in by_source.most_common()
    )
    if hidden_count:
        clusters.append(
            {
                "cluster_id": "hidden:limit",
                "label": "Hidden by limit",
                "count": hidden_count,
                "kind": "hidden",
            }
        )
    return clusters


async def build_knowledge_graph(
    session: AsyncSession,
    *,
    viewer_scope: str = SCOPE_FOUNDER,
    focus_node_id: str | None = None,
    depth: int = 1,
    node_type: str | None = None,
    relation_type: str | None = None,
    source_type: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    include_archived: bool = False,
    min_confidence: float | None = None,
    limit: int = DEFAULT_GRAPH_LIMIT,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or _now()
    safe_limit = _limit(limit)
    entity_rows = await _base_entities(session, include_archived=include_archived)
    nodes = [
        node
        for row in entity_rows
        if (
            node := await _entity_node(
                session,
                row,
                viewer_scope=viewer_scope,
                now=safe_now,
            )
        )
    ]
    node_type_by_id = {node["node_id"]: node["node_type"] for node in nodes}
    edges = [
        _edge_model(
            row,
            source_type=node_type_by_id.get(row.from_entity_id),
            target_type=node_type_by_id.get(row.to_entity_id),
            viewer_scope=viewer_scope,
        )
        for row in (await session.execute(select(EntityLinkRecord))).scalars().all()
    ]
    source_nodes, source_edges = await _source_event_virtuals(
        session, viewer_scope=viewer_scope, limit=safe_limit
    )
    normalized_nodes = await _normalized_virtuals(
        session, viewer_scope=viewer_scope, limit=safe_limit
    )
    finding_nodes, finding_edges = await _finding_virtuals(
        session, viewer_scope=viewer_scope, limit=safe_limit
    )
    proposal_nodes, proposal_edges = await _proposal_virtuals(
        session, viewer_scope=viewer_scope, limit=safe_limit
    )
    nodes.extend(source_nodes)
    nodes.extend(normalized_nodes)
    nodes.extend(finding_nodes)
    nodes.extend(proposal_nodes)
    edges.extend(source_edges)
    edges.extend(finding_edges)
    edges.extend(proposal_edges)

    nodes = _apply_node_filters(
        nodes,
        node_type=node_type,
        source_type=source_type,
        tag=tag,
        q=q,
        min_confidence=min_confidence,
    )
    node_ids = {node["node_id"] for node in nodes}
    edges = [
        edge
        for edge in _apply_edge_filters(
            edges, relation_type=relation_type, min_confidence=min_confidence
        )
        if edge["source_node_id"] in node_ids and edge["target_node_id"] in node_ids
    ]
    if focus_node_id:
        nodes, edges = _local_graph(
            nodes=nodes,
            edges=edges,
            focus_node_id=focus_node_id,
            depth=depth,
        )
    total_nodes = len(nodes)
    hidden_count = max(0, total_nodes - safe_limit)
    nodes = nodes[:safe_limit]
    visible_ids = {node["node_id"] for node in nodes}
    edges = [
        edge
        for edge in edges
        if edge["source_node_id"] in visible_ids and edge["target_node_id"] in visible_ids
    ]
    focus_node = next((node for node in nodes if node["node_id"] == focus_node_id), None)
    by_type = Counter(node["node_type"] for node in nodes)
    by_relation = Counter(edge["relation_type"] for edge in edges)
    return {
        "mode": "local" if focus_node_id else "global",
        "focus_node": focus_node,
        "nodes": nodes,
        "edges": edges,
        "clusters": _clusters(nodes, hidden_count),
        "filters": {
            "node_type": node_type,
            "relation_type": relation_type,
            "source_type": source_type,
            "tag": tag,
            "q": q,
            "include_archived": include_archived,
            "min_confidence": min_confidence,
            "depth": depth,
            "limit": safe_limit,
        },
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "hidden_count": hidden_count,
            "disputed_edges": sum(1 for edge in edges if edge.get("disputed")),
            "by_node_type": dict(by_type),
            "by_relation_type": dict(by_relation),
        },
        "legend": {
            "node_types": NODE_TYPE_LABELS,
            "relation_types": RELATION_LABELS,
            "size": "node evidence_count / importance",
            "glow": "freshness",
            "edge_thickness": "confidence",
            "dashed_edge": "disputed or low confidence",
        },
        "data_availability": {
            "status": "collecting" if not nodes else "ready",
            "message": "Knowledge graph is read from Postgres evidence-backed models.",
        },
        "redaction_manifest": _knowledge_redaction_manifest(
            viewer_scope,
            included_sections=["nodes", "edges", "clusters", "stats"],
            excluded_sections=["raw_source_bodies", "external_tokens"],
        ),
        "warnings": (
            ["graph capped; use local graph or filters to expand"]
            if hidden_count
            else []
        ),
    }


def _source_event_ids_from_refs(refs: list[Any]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        value = ref.get("source_event_id")
        if isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


def _normalized_ids_from_refs(refs: list[Any]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        value = ref.get("normalized_event_id")
        if isinstance(value, str) and value and value not in out:
            out.append(value)
    return out


async def _find_entity(session: AsyncSession, node_id: str) -> EntityRecord | None:
    return await session.scalar(select(EntityRecord).where(EntityRecord.entity_id == node_id))


async def _find_virtual_node(
    session: AsyncSession,
    node_id: str,
) -> tuple[str, Any] | None:
    if node_id.startswith("source_event:"):
        value = node_id.split(":", 1)[1]
        row = await session.scalar(select(SourceEvent).where(SourceEvent.source_event_id == value))
        return ("source_event", row) if row else None
    if node_id.startswith("normalized_event:"):
        value = node_id.split(":", 1)[1]
        row = await session.scalar(
            select(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id == value
            )
        )
        return ("normalized_event", row) if row else None
    if node_id.startswith("finding:"):
        value = node_id.split(":", 1)[1]
        row = await session.scalar(
            select(SecondOpinionFinding).where(SecondOpinionFinding.finding_key == value)
        )
        return ("finding", row) if row else None
    if node_id.startswith("proposal:"):
        value = node_id.split(":", 1)[1]
        row = await session.scalar(
            select(AgentProposal).where(AgentProposal.proposal_id == value)
        )
        return ("proposal", row) if row else None
    return None


async def _note_node(
    session: AsyncSession,
    node_id: str,
    *,
    viewer_scope: str,
    now: datetime,
) -> dict[str, Any] | None:
    entity = await _find_entity(session, node_id)
    if entity is not None:
        return await _entity_node(session, entity, viewer_scope=viewer_scope, now=now)
    virtual = await _find_virtual_node(session, node_id)
    if virtual is None:
        return None
    kind, row = virtual
    if kind == "source_event":
        if viewer_scope == SCOPE_INVESTOR:
            return None
        return _virtual_node(
            node_id=node_id,
            node_type="source_event",
            title=row.title or row.source_object_id,
            summary=row.summary,
            source_types=[row.source_system],
            created_by_run_id=row.created_by_run_id,
            last_observed_at=row.source_event_ts.isoformat() if row.source_event_ts else None,
            properties={
                "source_event_id": row.source_event_id,
                "source_system": row.source_system,
                "source_object_type": row.source_object_type,
                "source_object_id": row.source_object_id,
                "raw_object_ref": row.raw_object_ref,
                "source_url": row.source_url,
            },
            viewer_scope=viewer_scope,
        )
    if kind == "normalized_event":
        if viewer_scope == SCOPE_INVESTOR:
            return None
        return _virtual_node(
            node_id=node_id,
            node_type="normalized_event",
            title=row.title or row.source_object_id,
            summary=row.safe_summary,
            source_types=[row.source],
            created_by_run_id=row.run_id,
            last_observed_at=row.activity_created_at.isoformat() if row.activity_created_at else None,
            properties={
                "activity_item_id": row.activity_item_id,
                "source_event_id": row.source_event_id,
                "activity_type": row.activity_type,
                "project": row.project,
            },
            viewer_scope=viewer_scope,
        )
    if kind == "finding":
        if viewer_scope == SCOPE_INVESTOR:
            return None
        return _virtual_node(
            node_id=node_id,
            node_type="finding",
            title=row.summary,
            summary=row.observed_state,
            source_types=["second_opinion"],
            evidence_count=len(row.evidence_refs or []),
            confidence=float(row.confidence or 0.0),
            created_by_run_id=row.last_run_id,
            properties={
                "finding_key": row.finding_key,
                "finding_type": row.finding_type,
                "severity": row.severity,
                "status": row.status,
                "evidence_refs": row.evidence_refs,
            },
            viewer_scope=viewer_scope,
        )
    if viewer_scope == SCOPE_INVESTOR:
        return None
    return _virtual_node(
        node_id=node_id,
        node_type="proposal",
        title=row.title,
        summary=f"{row.kind} waiting for review",
        source_types=[row.agent],
        evidence_count=len(row.evidence_refs or []),
        confidence=float(row.confidence or 0.0),
        created_by_run_id=row.run_id,
        properties={
            "proposal_id": row.proposal_id,
            "proposal_type": row.kind,
            "status": row.status,
            "payload": row.payload,
            "evidence_refs": row.evidence_refs,
        },
        viewer_scope=viewer_scope,
    )


async def build_knowledge_node_note(
    session: AsyncSession,
    *,
    node_id: str,
    viewer_scope: str = SCOPE_FOUNDER,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    safe_now = now or _now()
    node = await _note_node(session, node_id, viewer_scope=viewer_scope, now=safe_now)
    if node is None:
        return None
    graph = await build_knowledge_graph(
        session,
        viewer_scope=viewer_scope,
        focus_node_id=node_id,
        depth=1,
        limit=120,
        now=safe_now,
    )
    backlinks = [
        edge for edge in graph["edges"] if edge["target_node_id"] == node_id
    ]
    outgoing = [
        edge for edge in graph["edges"] if edge["source_node_id"] == node_id
    ]
    refs = _as_list(node.get("source_refs")) + _as_list(node.get("properties", {}).get("source_refs"))
    source_event_ids = _source_event_ids_from_refs(refs)
    normalized_event_ids = _normalized_ids_from_refs(refs)
    related_findings = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(
                or_(
                    SecondOpinionFinding.entity_id == node_id,
                    cast(SecondOpinionFinding.evidence_refs, Text).like(f"%{node_id}%"),
                )
            )
            .order_by(SecondOpinionFinding.updated_at.desc())
            .limit(20)
        )
    ).scalars().all()
    related_proposals = (
        await session.execute(
            select(AgentProposal)
            .where(
                or_(
                    cast(AgentProposal.payload, Text).like(f"%{node_id}%"),
                    cast(AgentProposal.evidence_refs, Text).like(f"%{node_id}%"),
                )
            )
            .order_by(AgentProposal.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    source_events = []
    if viewer_scope != SCOPE_INVESTOR and source_event_ids:
        source_events = [
            {
                "source_event_id": row.source_event_id,
                "source_system": row.source_system,
                "event_type": row.event_type,
                "title": row.title,
                "received_at": row.created_at.isoformat() if row.created_at else None,
                **({"raw_object_ref": row.raw_object_ref} if viewer_scope == SCOPE_FOUNDER else {}),
            }
            for row in (
                await session.execute(
                    select(SourceEvent)
                    .where(SourceEvent.source_event_id.in_(source_event_ids))
                    .limit(20)
                )
            ).scalars().all()
        ]
    normalized_events = []
    if viewer_scope != SCOPE_INVESTOR and normalized_event_ids:
        normalized_events = [
            {
                "activity_item_id": row.activity_item_id,
                "source": row.source,
                "activity_type": row.activity_type,
                "title": row.title,
                "occurred_at": row.activity_created_at.isoformat() if row.activity_created_at else None,
            }
            for row in (
                await session.execute(
                    select(NormalizedActivityItemRecord)
                    .where(NormalizedActivityItemRecord.activity_item_id.in_(normalized_event_ids))
                    .limit(20)
                )
            ).scalars().all()
        ]
    run_ids = [
        value
        for value in (node.get("created_by_run_id"), node.get("updated_by_run_id"))
        if isinstance(value, str) and value
    ]
    source_runs = []
    if run_ids and viewer_scope == SCOPE_FOUNDER:
        source_runs = [
            {
                "request_id": row.request_id,
                "run_id": row.run_id,
                "source_type": row.source_type,
                "action_type": row.action_type,
                "status": row.status,
                "result_summary": sanitize_for_logs(row.result_summary or {}),
            }
            for row in (
                await session.execute(
                    select(SourceRunRequest).where(SourceRunRequest.run_id.in_(run_ids)).limit(20)
                )
            ).scalars().all()
        ]
    findings = [
        {
            "finding_key": row.finding_key,
            "finding_type": row.finding_type,
            "summary": row.summary,
            "severity": row.severity,
            "confidence": row.confidence,
            "status": row.status,
        }
        for row in related_findings
        if viewer_scope != SCOPE_INVESTOR
    ]
    proposals = [
        {
            "proposal_id": row.proposal_id,
            "proposal_type": row.kind,
            "title": row.title,
            "confidence": row.confidence,
            "status": row.status,
        }
        for row in related_proposals
        if viewer_scope != SCOPE_INVESTOR
    ]
    timeline = sorted(
        [
            {"kind": "source_event", "at": item.get("received_at"), "title": item.get("title")}
            for item in source_events
        ]
        + [
            {"kind": "normalized_event", "at": item.get("occurred_at"), "title": item.get("title")}
            for item in normalized_events
        ],
        key=lambda item: str(item.get("at") or ""),
    )
    return {
        "node": node,
        "title": node["title"],
        "type": node["node_type"],
        "summary": node.get("summary"),
        "properties": node.get("properties") or {},
        "tags": node.get("tags") or [],
        "backlinks": backlinks,
        "outgoing_links": outgoing,
        "evidence": {
            "evidence_count": node.get("evidence_count") or 0,
            "source_event_ids": source_event_ids if viewer_scope == SCOPE_FOUNDER else [],
            "normalized_event_ids": normalized_event_ids if viewer_scope != SCOPE_INVESTOR else [],
        },
        "source_events": source_events,
        "normalized_events": normalized_events,
        "related_findings": findings,
        "related_proposals": proposals,
        "decisions": [edge for edge in backlinks + outgoing if edge["relation_type"] == "decided_in"],
        "tasks": [
            edge
            for edge in backlinks + outgoing
            if edge.get("target_node_type") in {"task", "issue", "pull_request"}
        ],
        "risks": [
            edge
            for edge in backlinks + outgoing
            if edge.get("target_node_type") == "risk"
        ],
        "timeline": timeline,
        "confidence_explanation": node.get("confidence_explanation")
        or explain_confidence(float(node.get("confidence") or 0.0), {}),
        "freshness": node.get("freshness"),
        "data_availability": {
            "status": "ready" if node.get("evidence_count") else "insufficient",
            "message": "Note is generated from evidence-backed graph rows.",
        },
        "redaction_manifest": _knowledge_redaction_manifest(
            viewer_scope,
            included_sections=["properties", "links", "evidence", "timeline"],
            excluded_sections=["raw_source_bodies", "external_tokens"],
        ),
        "audit_history": source_runs,
        "suggested_actions": [
            {
                "action": "review_proposal",
                "proposal_id": item["proposal_id"],
                "title": item["title"],
            }
            for item in proposals[:5]
        ],
        "local_graph": graph,
    }


def _wiki_title(title: str) -> str:
    cleaned = sanitize_obsidian_filename(title, fallback="Untitled", max_length=80)
    return cleaned or "Untitled"


def _frontmatter(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": node["node_id"],
        "node_type": node["node_type"],
        "tags": node.get("tags") or [],
        "evidence_count": node.get("evidence_count") or 0,
        "confidence": node.get("confidence"),
        "freshness": node.get("freshness"),
        "created_by_run_id": node.get("created_by_run_id"),
        "updated_by_run_id": node.get("updated_by_run_id"),
    }


def _render_markdown_file(
    node: dict[str, Any],
    outgoing: list[dict[str, Any]],
    node_titles: dict[str, str],
) -> dict[str, Any]:
    title = _wiki_title(node["title"])
    directory = {
        "project": "Projects",
        "person": "People",
        "task": "Tasks",
        "issue": "Tasks",
        "pull_request": "Code",
        "repo": "Repos",
        "decision": "Decisions",
        "risk": "Risks",
        "hypothesis": "Hypotheses",
        "finding": "Findings",
        "proposal": "Proposals",
        "source_event": "Sources",
        "normalized_event": "Evidence",
    }.get(node["node_type"], "Knowledge")
    path = f"{directory}/{title}.md"
    frontmatter = sanitize_for_logs(_frontmatter(node))
    links = [
        f"[[{_wiki_title(node_titles[target])}]]"
        for target in [edge["target_node_id"] for edge in outgoing]
        if target in node_titles
    ]
    body_lines = [
        f"# {title}",
        "",
        node.get("summary") or "No summary yet.",
        "",
        "## Properties",
        "",
        f"- Type: `{node['node_type']}`",
        f"- Evidence: {node.get('evidence_count') or 0}",
        f"- Confidence: {node.get('confidence')}",
        "",
        "## Links",
        "",
        *(f"- {link}" for link in links),
        "",
        "## Evidence",
        "",
        "- See FounderOS Evidence Trail for source lineage.",
    ]
    body = "\n".join(body_lines).rstrip() + "\n"
    return {
        "path": path,
        "title": title,
        "frontmatter": frontmatter,
        "body": body,
        "links": links,
        "redaction": {"raw_refs_included": False, "raw_bodies_included": False},
        "content_hash": _stable_hash({"frontmatter": frontmatter, "body": body}),
    }


async def build_obsidian_preview(
    session: AsyncSession,
    *,
    viewer_scope: str = SCOPE_FOUNDER,
    limit: int = 80,
) -> dict[str, Any]:
    if viewer_scope != SCOPE_FOUNDER:
        return {
            "vault_name": "FounderOS Knowledge Vault",
            "files": [],
            "manifest": {
                "status": "blocked",
                "reason": "founder view required",
                "file_write_performed": False,
            },
            "warnings": ["Obsidian preview is founder-only by default."],
        }
    graph = await build_knowledge_graph(session, viewer_scope=viewer_scope, limit=limit)
    node_titles = {node["node_id"]: node["title"] for node in graph["nodes"]}
    edges_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph["edges"]:
        edges_by_source[edge["source_node_id"]].append(edge)
    files = [
        _render_markdown_file(node, edges_by_source.get(node["node_id"], []), node_titles)
        for node in graph["nodes"][:limit]
    ]
    return {
        "vault_name": "FounderOS Knowledge Vault",
        "files": files,
        "manifest": {
            "file_write_performed": False,
            "source": "postgres_read_model",
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "content_hash": _stable_hash([file["content_hash"] for file in files]),
            "redaction": _knowledge_redaction_manifest(
                viewer_scope,
                included_sections=["frontmatter", "wikilinks", "evidence_summary"],
                excluded_sections=["raw_source_bodies", "external_tokens"],
            ),
        },
        "warnings": graph.get("warnings", []),
    }
