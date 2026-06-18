"""Lift normalized evidence into graph, proposals, findings and run summaries.

The Stage 12 pipeline is deterministic and provider-free. It reads persisted
``normalized_activity_items`` rows, writes only local graph/proposal/finding
state with evidence refs, and records a sanitized run log/audit row.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentRunLog
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.models import AuditLog
from app.db.source_control_models import SourceRunRequest
from app.services.agent_proposals import create_proposal
from app.services.browser_config import sanitize_for_logs
from app.services.confidence import build_confidence
from app.services.entity_identity import register_source_account, suggest_person_merges
from app.services.knowledge_graph import (
    ENTITY_CLIENT,
    ENTITY_DECISION,
    ENTITY_HYPOTHESIS,
    ENTITY_MEETING,
    ENTITY_PERSON,
    ENTITY_PROJECT,
    ENTITY_REPOSITORY,
    ENTITY_TASK,
    ENTITY_TYPES,
    REL_BELONGS_TO,
    REL_MENTIONS,
    REL_WORKS_ON,
    RELATIONS,
    link_id as graph_link_id,
    person_entity_id,
    slugify,
    upsert_alias,
)
from app.services.run_context import get_run_id, set_run_id
from app.services.second_opinion import (
    FINDING_EXECUTION_MISMATCH,
    FINDING_OWNERSHIP_GAP,
    emit_finding_or_proposal,
    tally_outcome,
)

AGENT_NAME = "evidence_pipeline"
AGENT_VERSION = "stage12.mvp"
CONFIDENCE_AUTO_LINK_THRESHOLD = 0.65
PROJECT_HINT_RE = re.compile(r"\b(Project\s+[A-Z][A-Za-z0-9-]*)\b")


@dataclass
class EvidencePipelineSummary:
    normalized_events_seen: int = 0
    normalized_events_processed: int = 0
    graph_nodes_created: int = 0
    graph_nodes_updated: int = 0
    graph_edges_created: int = 0
    graph_edges_updated: int = 0
    merge_proposals_created: int = 0
    link_proposals_created: int = 0
    findings_created: int = 0
    findings_updated_from_new_evidence: int = 0
    findings_updated_from_clock_recalculation: int = 0
    findings_auto_resolved: int = 0
    findings_proposed: int = 0
    data_quality_issues_created: int = 0
    skipped_low_confidence: int = 0
    skipped_no_evidence: int = 0
    skipped_archived: int = 0
    unchanged: int = 0
    errors: int = 0
    run_started_at: str | None = None
    run_finished_at: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    processed_activity_item_ids: list[str] = field(default_factory=list)
    source_run_ids: list[str] = field(default_factory=list)
    error_summaries: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_events_seen": self.normalized_events_seen,
            "normalized_events_processed": self.normalized_events_processed,
            "graph_nodes_created": self.graph_nodes_created,
            "graph_nodes_updated": self.graph_nodes_updated,
            "graph_edges_created": self.graph_edges_created,
            "graph_edges_updated": self.graph_edges_updated,
            "merge_proposals_created": self.merge_proposals_created,
            "link_proposals_created": self.link_proposals_created,
            "findings_created": self.findings_created,
            "findings_updated_from_new_evidence": self.findings_updated_from_new_evidence,
            "findings_updated_from_clock_recalculation": self.findings_updated_from_clock_recalculation,
            "findings_auto_resolved": self.findings_auto_resolved,
            "findings_proposed": self.findings_proposed,
            "data_quality_issues_created": self.data_quality_issues_created,
            "skipped_low_confidence": self.skipped_low_confidence,
            "skipped_no_evidence": self.skipped_no_evidence,
            "skipped_archived": self.skipped_archived,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "run_started_at": self.run_started_at,
            "run_finished_at": self.run_finished_at,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "processed_activity_item_ids": list(self.processed_activity_item_ids),
            "source_run_ids": list(self.source_run_ids),
            "error_summaries": list(self.error_summaries),
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hash(value: Any, *, prefix: str = "") -> str:
    digest = hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}{digest}" if prefix else digest


def _bounded_id(value: str, *, prefix: str, max_chars: int = 120) -> str:
    if len(value) <= max_chars:
        return value
    return f"{prefix}:{_hash(value)}"


def _safe_str(value: Any, *, max_chars: int = 500) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text[:max_chars] or None


def _unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _merge_list(existing: Any, additions: list[Any]) -> list[Any]:
    base = existing if isinstance(existing, list) else []
    out: list[Any] = []
    seen: set[str] = set()
    for item in [*base, *additions]:
        marker = _stable_json(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _source_metadata(source_event: SourceEvent | None) -> dict[str, Any]:
    metadata = source_event.metadata_json if source_event and isinstance(source_event.metadata_json, dict) else {}
    return metadata if isinstance(metadata, dict) else {}


def _evidence_ref(
    item: NormalizedActivityItemRecord,
    source_event: SourceEvent | None,
) -> dict[str, Any]:
    metadata = _source_metadata(source_event)
    return {
        "kind": "normalized_activity",
        "normalized_event_id": item.activity_item_id,
        "source_event_id": item.source_event_id,
        "source_type": item.source,
        "source_object_id": item.source_object_id,
        "activity_type": item.activity_type,
        "source_run_id": source_event.created_by_run_id if source_event else item.run_id,
        "correlation_id": metadata.get("correlation_id"),
    }


def _source_run_id(item: NormalizedActivityItemRecord, source_event: SourceEvent | None) -> str | None:
    return source_event.created_by_run_id if source_event and source_event.created_by_run_id else item.run_id


async def _source_event_for_item(
    session: AsyncSession,
    item: NormalizedActivityItemRecord,
) -> SourceEvent | None:
    if not item.source_event_id:
        return None
    return await session.scalar(
        select(SourceEvent).where(SourceEvent.source_event_id == item.source_event_id)
    )


def _entity_attrs(
    *,
    item: NormalizedActivityItemRecord,
    evidence_ref: dict[str, Any],
    confidence: float,
    entity_role: str,
    visibility_scope: str = "founder",
) -> dict[str, Any]:
    observed = item.activity_created_at or item.created_at
    return {
        "source_types": [item.source],
        "source_refs": [evidence_ref],
        "source_event_ids": [item.source_event_id] if item.source_event_id else [],
        "normalized_event_ids": [item.activity_item_id],
        "evidence_count": 1,
        "confidence": confidence,
        "visibility_scope": visibility_scope,
        "last_observed_at": observed.isoformat() if observed else None,
        "entity_role": entity_role,
        "generated_by_pipeline": AGENT_NAME,
    }


async def _upsert_entity_with_lineage(
    session: AsyncSession,
    *,
    entity_id: str,
    entity_type: str,
    canonical_name: str,
    attrs: dict[str, Any],
) -> str:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type: {entity_type}")
    run_id = get_run_id()
    existing = await session.scalar(
        select(EntityRecord).where(EntityRecord.entity_id == entity_id)
    )
    if existing is None:
        session.add(
            EntityRecord(
                entity_id=entity_id,
                entity_type=entity_type,
                canonical_name=canonical_name[:255],
                attrs=sanitize_for_logs(dict(attrs)),
                created_by_run_id=run_id,
                updated_by_run_id=run_id,
            )
        )
        await session.flush()
        return "created"
    if (existing.attrs or {}).get("archived"):
        return "archived"

    merged = dict(existing.attrs or {})
    changed = False
    for key, value in attrs.items():
        if isinstance(value, list):
            combined = _merge_list(merged.get(key), value)
            if combined != merged.get(key):
                merged[key] = combined
                changed = True
        elif key == "evidence_count":
            new_count = max(int(merged.get(key) or 0), int(value or 0))
            if merged.get(key) != new_count:
                merged[key] = new_count
                changed = True
        elif value is not None and merged.get(key) != value:
            merged[key] = value
            changed = True
    cleaned_name = canonical_name[:255]
    if cleaned_name and existing.canonical_name != cleaned_name:
        existing.canonical_name = cleaned_name
        changed = True
    if changed:
        existing.attrs = sanitize_for_logs(merged)
        existing.updated_by_run_id = run_id
        await session.flush()
        return "updated"
    return "unchanged"


def _relation_payload(
    *,
    item: NormalizedActivityItemRecord,
    evidence_refs: list[dict[str, Any]],
    confidence: float,
    relation_role: str,
) -> dict[str, Any]:
    observed = item.activity_created_at or item.created_at
    return {
        "confidence": confidence,
        "confidence_factors": {
            "source": "normalized_activity",
            "relation_role": relation_role,
            "evidence_count": len(evidence_refs),
            "source_event_ids": _unique(
                [str(ref.get("source_event_id") or "") for ref in evidence_refs]
            ),
            "normalized_event_ids": _unique(
                [str(ref.get("normalized_event_id") or "") for ref in evidence_refs]
            ),
            "last_observed_at": observed.isoformat() if observed else None,
            "generated_by_pipeline": AGENT_NAME,
            "updated_by_run_id": get_run_id(),
        },
    }


async def _upsert_link_or_propose(
    session: AsyncSession,
    *,
    item: NormalizedActivityItemRecord,
    from_entity_id: str,
    relation: str,
    to_entity_id: str,
    evidence_refs: list[dict[str, Any]],
    confidence: float,
    relation_role: str,
    title: str,
) -> str:
    if not evidence_refs:
        return "no_evidence"
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation: {relation}")

    raw_lid = graph_link_id(from_entity_id, relation, to_entity_id)
    lid = _bounded_id(raw_lid, prefix="link")
    payload = _relation_payload(
        item=item,
        evidence_refs=evidence_refs,
        confidence=confidence,
        relation_role=relation_role,
    )
    if confidence < CONFIDENCE_AUTO_LINK_THRESHOLD:
        proposal_id = f"relation:{_hash({'from': from_entity_id, 'rel': relation, 'to': to_entity_id}, prefix='')}"
        created = await create_proposal(
            session,
            proposal_id=proposal_id,
            dedupe_key=proposal_id,
            agent=AGENT_NAME,
            kind="low_confidence_relation",
            title=title[:490],
            payload={
                "from_entity_id": from_entity_id,
                "relation": relation,
                "to_entity_id": to_entity_id,
                "would_create_link_id": lid,
                "requires_approval": True,
            },
            evidence_refs=evidence_refs,
            confidence=confidence,
            confidence_factors=payload["confidence_factors"],
            source_snapshot={
                "relation_role": relation_role,
                "source_event_ids": payload["confidence_factors"]["source_event_ids"],
                "normalized_event_ids": payload["confidence_factors"]["normalized_event_ids"],
            },
        )
        return "proposed" if created else "proposal_exists"

    existing = await session.scalar(
        select(EntityLinkRecord).where(EntityLinkRecord.link_id == lid)
    )
    if existing is None:
        session.add(
            EntityLinkRecord(
                link_id=lid,
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                relation=relation,
                evidence_refs=evidence_refs,
                confidence=confidence,
                confidence_factors=payload["confidence_factors"],
                created_by_run_id=get_run_id(),
            )
        )
        await session.flush()
        return "created"

    changed = False
    combined_refs = _merge_list(existing.evidence_refs, evidence_refs)
    if combined_refs != (existing.evidence_refs or []):
        existing.evidence_refs = combined_refs
        changed = True
    if confidence > float(existing.confidence or 0.0):
        existing.confidence = confidence
        changed = True
    factors = dict(existing.confidence_factors or {})
    for key, value in payload["confidence_factors"].items():
        if isinstance(value, list):
            combined = _merge_list(factors.get(key), value)
            if combined != factors.get(key):
                factors[key] = combined
                changed = True
        elif factors.get(key) != value:
            factors[key] = value
            changed = True
    if changed:
        existing.confidence_factors = sanitize_for_logs(factors)
        await session.flush()
        return "updated"
    return "unchanged"


def _work_item_entity(item: NormalizedActivityItemRecord) -> tuple[str, str, str]:
    title = _safe_str(item.title or item.source_object_id) or item.source_object_id
    if item.source == "github":
        return (
            _bounded_id(
                f"{ENTITY_TASK}:github:{slugify(item.source_object_id)}",
                prefix=ENTITY_TASK,
            ),
            ENTITY_TASK,
            title,
        )
    if item.source == "jira":
        return (
            _bounded_id(
                f"{ENTITY_TASK}:jira:{slugify(item.source_object_id)}",
                prefix=ENTITY_TASK,
            ),
            ENTITY_TASK,
            title,
        )
    if item.source == "gmail":
        return (
            _bounded_id(
                f"{ENTITY_CLIENT}:gmail:{slugify(item.source_object_id)}",
                prefix=ENTITY_CLIENT,
            ),
            ENTITY_CLIENT,
            title,
        )
    if item.source in {"meeting", "meetings", "calendar", "drive"} or "meeting" in item.activity_type:
        return (
            _bounded_id(f"{ENTITY_MEETING}:{slugify(item.source_object_id)}", prefix=ENTITY_MEETING),
            ENTITY_MEETING,
            title,
        )
    if "hypothesis" in f"{item.activity_type} {item.title or ''}".casefold():
        return (
            _bounded_id(
                f"{ENTITY_HYPOTHESIS}:{slugify(item.source_object_id)}",
                prefix=ENTITY_HYPOTHESIS,
            ),
            ENTITY_HYPOTHESIS,
            title,
        )
    return (
        _bounded_id(
            f"{ENTITY_DECISION}:{slugify(item.source_object_id)}",
            prefix=ENTITY_DECISION,
        ),
        ENTITY_DECISION,
        title,
    )


def _project_from_item(item: NormalizedActivityItemRecord) -> tuple[str, float, str] | None:
    if item.project:
        return item.project, 0.85, "explicit_project"
    text = " ".join(
        value
        for value in (item.title, item.safe_summary)
        if isinstance(value, str)
    )
    match = PROJECT_HINT_RE.search(text)
    if match:
        return match.group(1), 0.4, "text_project_hint"
    return None


def _repository_from_item(item: NormalizedActivityItemRecord) -> str | None:
    if item.source != "github":
        return None
    for value in [item.source_object_id, *list(item.related_prs or [])]:
        if not value:
            continue
        text = str(value)
        if "/" in text:
            candidate = text.split("/pull/", 1)[0].split("#", 1)[0]
            if "/" in candidate:
                return candidate.strip("/")
    return None


async def lift_normalized_activity_item(
    session: AsyncSession,
    item: NormalizedActivityItemRecord,
) -> dict[str, int]:
    counts = {
        "processed": 0,
        "nodes_created": 0,
        "nodes_updated": 0,
        "edges_created": 0,
        "edges_updated": 0,
        "link_proposals_created": 0,
        "findings_created": 0,
        "findings_updated_from_new_evidence": 0,
        "findings_updated_from_clock_recalculation": 0,
        "findings_proposed": 0,
        "skipped_low_confidence": 0,
        "skipped_no_evidence": 0,
        "skipped_archived": 0,
        "unchanged": 0,
        "errors": 0,
    }
    source_event = await _source_event_for_item(session, item)
    if not item.source_event_id or source_event is None:
        counts["skipped_no_evidence"] += 1
        return counts

    evidence_ref = _evidence_ref(item, source_event)
    work_entity_id, work_type, work_name = _work_item_entity(item)
    outcome = await _upsert_entity_with_lineage(
        session,
        entity_id=work_entity_id,
        entity_type=work_type,
        canonical_name=work_name,
        attrs=_entity_attrs(
            item=item,
            evidence_ref=evidence_ref,
            confidence=0.85,
            entity_role="activity_object",
        ),
    )
    _tally_entity_outcome(counts, outcome)
    counts["processed"] += 1

    actor_entity_id: str | None = None
    actor = _safe_str(item.actor, max_chars=160)
    if actor:
        actor_entity_id = _bounded_id(person_entity_id(actor), prefix=ENTITY_PERSON)
        outcome = await _upsert_entity_with_lineage(
            session,
            entity_id=actor_entity_id,
            entity_type=ENTITY_PERSON,
            canonical_name=actor,
            attrs=_entity_attrs(
                item=item,
                evidence_ref=evidence_ref,
                confidence=0.8,
                entity_role="actor",
            ),
        )
        _tally_entity_outcome(counts, outcome)
        await upsert_alias(session, entity_id=actor_entity_id, alias=actor, source=item.source)
        await register_source_account(
            session,
            entity_id=actor_entity_id,
            source_system=item.source,
            account_id=actor,
            confidence=0.8,
        )

    project_hint = _project_from_item(item)
    project_entity_id: str | None = None
    if project_hint is not None:
        project_name, confidence, hint_type = project_hint
        project_entity_id = _bounded_id(
            f"{ENTITY_PROJECT}:{slugify(project_name)}",
            prefix=ENTITY_PROJECT,
        )
        outcome = await _upsert_entity_with_lineage(
            session,
            entity_id=project_entity_id,
            entity_type=ENTITY_PROJECT,
            canonical_name=project_name,
            attrs=_entity_attrs(
                item=item,
                evidence_ref=evidence_ref,
                confidence=confidence,
                entity_role="project_hint",
            ),
        )
        _tally_entity_outcome(counts, outcome)
        relation_outcome = await _upsert_link_or_propose(
            session,
            item=item,
            from_entity_id=work_entity_id,
            relation=REL_MENTIONS,
            to_entity_id=project_entity_id,
            evidence_refs=[evidence_ref],
            confidence=confidence,
            relation_role=hint_type,
            title=f"Review project relation: {work_name} -> {project_name}",
        )
        _tally_link_outcome(counts, relation_outcome)
        if actor_entity_id:
            relation_outcome = await _upsert_link_or_propose(
                session,
                item=item,
                from_entity_id=actor_entity_id,
                relation=REL_WORKS_ON,
                to_entity_id=project_entity_id,
                evidence_refs=[evidence_ref],
                confidence=max(0.4, confidence - 0.1),
                relation_role=f"actor_{hint_type}",
                title=f"Review actor project relation: {actor} -> {project_name}",
            )
            _tally_link_outcome(counts, relation_outcome)

    repository = _repository_from_item(item)
    if repository:
        repo_entity_id = _bounded_id(
            f"{ENTITY_REPOSITORY}:{slugify(repository)}",
            prefix=ENTITY_REPOSITORY,
        )
        outcome = await _upsert_entity_with_lineage(
            session,
            entity_id=repo_entity_id,
            entity_type=ENTITY_REPOSITORY,
            canonical_name=repository,
            attrs=_entity_attrs(
                item=item,
                evidence_ref=evidence_ref,
                confidence=0.9,
                entity_role="repository",
            ),
        )
        _tally_entity_outcome(counts, outcome)
        relation_outcome = await _upsert_link_or_propose(
            session,
            item=item,
            from_entity_id=work_entity_id,
            relation=REL_MENTIONS,
            to_entity_id=repo_entity_id,
            evidence_refs=[evidence_ref],
            confidence=0.9,
            relation_role="github_repository_activity",
            title=f"Link GitHub activity to repository {repository}",
        )
        _tally_link_outcome(counts, relation_outcome)
        if project_entity_id and project_hint and project_hint[1] >= CONFIDENCE_AUTO_LINK_THRESHOLD:
            relation_outcome = await _upsert_link_or_propose(
                session,
                item=item,
                from_entity_id=repo_entity_id,
                relation=REL_BELONGS_TO,
                to_entity_id=project_entity_id,
                evidence_refs=[evidence_ref],
                confidence=0.75,
                relation_role="repo_project_observed_together",
                title=f"Link repository {repository} to {project_hint[0]}",
            )
            _tally_link_outcome(counts, relation_outcome)

    for key in item.related_jira_keys or []:
        issue_entity_id = _bounded_id(
            f"{ENTITY_TASK}:jira:{slugify(key)}",
            prefix=ENTITY_TASK,
        )
        outcome = await _upsert_entity_with_lineage(
            session,
            entity_id=issue_entity_id,
            entity_type=ENTITY_TASK,
            canonical_name=key,
            attrs=_entity_attrs(
                item=item,
                evidence_ref=evidence_ref,
                confidence=0.8,
                entity_role="related_jira_key",
            ),
        )
        _tally_entity_outcome(counts, outcome)
        relation_outcome = await _upsert_link_or_propose(
            session,
            item=item,
            from_entity_id=work_entity_id,
            relation=REL_MENTIONS,
            to_entity_id=issue_entity_id,
            evidence_refs=[evidence_ref],
            confidence=0.8,
            relation_role="explicit_jira_key",
            title=f"Link activity to Jira key {key}",
        )
        _tally_link_outcome(counts, relation_outcome)

    await _emit_findings(session, item=item, work_entity_id=work_entity_id, evidence_ref=evidence_ref, counts=counts)
    return counts


def _tally_entity_outcome(counts: dict[str, int], outcome: str) -> None:
    if outcome == "created":
        counts["nodes_created"] += 1
    elif outcome == "updated":
        counts["nodes_updated"] += 1
    elif outcome == "archived":
        counts["skipped_archived"] += 1
    elif outcome == "unchanged":
        counts["unchanged"] += 1


def _tally_link_outcome(counts: dict[str, int], outcome: str) -> None:
    if outcome == "created":
        counts["edges_created"] += 1
    elif outcome == "updated":
        counts["edges_updated"] += 1
    elif outcome == "proposed":
        counts["link_proposals_created"] += 1
        counts["skipped_low_confidence"] += 1
    elif outcome == "proposal_exists":
        counts["skipped_low_confidence"] += 1
    elif outcome == "no_evidence":
        counts["skipped_no_evidence"] += 1
    elif outcome == "unchanged":
        counts["unchanged"] += 1


async def _emit_findings(
    session: AsyncSession,
    *,
    item: NormalizedActivityItemRecord,
    work_entity_id: str,
    evidence_ref: dict[str, Any],
    counts: dict[str, int],
) -> None:
    if not evidence_ref.get("source_event_id"):
        counts["skipped_no_evidence"] += 1
        return
    evidence_refs = [evidence_ref]
    source_refs = [
        {
            "kind": "graph_entity",
            "entity_id": work_entity_id,
            "normalized_event_id": item.activity_item_id,
        }
    ]
    if item.source == "github" and "pull_request" in item.activity_type and not item.related_jira_keys:
        score, factors = build_confidence(
            evidence_count=1,
            source_quality=1.0,
            freshness=1.0,
            cross_source_match=False,
        )
        outcome = await emit_finding_or_proposal(
            session,
            agent=AGENT_NAME,
            finding_kwargs={
                "finding_key": f"{work_entity_id}:execution_mismatch:no_jira",
                "entity_id": work_entity_id,
                "finding_type": FINDING_EXECUTION_MISMATCH,
                "declared_state": "GitHub PR carries engineering activity",
                "observed_state": "No Jira key is linked in normalized evidence",
                "summary": f"GitHub activity lacks Jira linkage: {item.title or item.source_object_id}",
                "severity": "medium",
                "confidence": score,
                "confidence_factors": factors,
                "evidence_refs": evidence_refs,
                "source_refs": source_refs,
                "visibility_scope": "team",
            },
        )
        _tally_finding_outcome(counts, outcome)
    if item.source == "jira" and not item.actor:
        score, factors = build_confidence(
            evidence_count=1,
            source_quality=1.0,
            freshness=1.0,
            cross_source_match=False,
        )
        outcome = await emit_finding_or_proposal(
            session,
            agent=AGENT_NAME,
            finding_kwargs={
                "finding_key": f"{work_entity_id}:ownership_gap:no_actor",
                "entity_id": work_entity_id,
                "finding_type": FINDING_OWNERSHIP_GAP,
                "declared_state": "Jira issue exists as active work",
                "observed_state": "No owner/actor is attached to the normalized event",
                "summary": f"Jira work has no owner signal: {item.title or item.source_object_id}",
                "severity": "low",
                "confidence": score,
                "confidence_factors": factors,
                "evidence_refs": evidence_refs,
                "source_refs": source_refs,
                "visibility_scope": "team",
            },
        )
        _tally_finding_outcome(counts, outcome)


def _tally_finding_outcome(counts: dict[str, int], outcome: str) -> None:
    local = {
        "created": 0,
        "updated_from_new_evidence": 0,
        "updated_from_clock_recalculation": 0,
        "unchanged": 0,
        "reopened": 0,
        "auto_resolved": 0,
        "skipped": 0,
        "errors": 0,
    }
    if outcome == "proposed":
        counts["findings_proposed"] += 1
        return
    if outcome == "proposal_exists":
        return
    if outcome == "no_evidence":
        counts["skipped_no_evidence"] += 1
        return
    if outcome == "reopened":
        counts["findings_created"] += 1
        return
    tally_outcome(local, outcome)
    counts["findings_created"] += local["created"] + local["reopened"]
    counts["findings_updated_from_new_evidence"] += local["updated_from_new_evidence"]
    counts["findings_updated_from_clock_recalculation"] += local[
        "updated_from_clock_recalculation"
    ]
    counts["unchanged"] += local["unchanged"] + local["skipped"]
    counts["errors"] += local["errors"]


def _add_item_counts(summary: EvidencePipelineSummary, counts: dict[str, int]) -> None:
    summary.normalized_events_processed += counts.get("processed", 0)
    summary.graph_nodes_created += counts.get("nodes_created", 0)
    summary.graph_nodes_updated += counts.get("nodes_updated", 0)
    summary.graph_edges_created += counts.get("edges_created", 0)
    summary.graph_edges_updated += counts.get("edges_updated", 0)
    summary.link_proposals_created += counts.get("link_proposals_created", 0)
    summary.findings_created += counts.get("findings_created", 0)
    summary.findings_updated_from_new_evidence += counts.get(
        "findings_updated_from_new_evidence", 0
    )
    summary.findings_updated_from_clock_recalculation += counts.get(
        "findings_updated_from_clock_recalculation", 0
    )
    summary.findings_proposed += counts.get("findings_proposed", 0)
    summary.skipped_low_confidence += counts.get("skipped_low_confidence", 0)
    summary.skipped_no_evidence += counts.get("skipped_no_evidence", 0)
    summary.skipped_archived += counts.get("skipped_archived", 0)
    summary.unchanged += counts.get("unchanged", 0)
    summary.errors += counts.get("errors", 0)


def _compact_source_run_summary(summary: EvidencePipelineSummary) -> dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "graph_nodes_created": summary.graph_nodes_created,
        "graph_nodes_updated": summary.graph_nodes_updated,
        "graph_edges_created": summary.graph_edges_created,
        "graph_edges_updated": summary.graph_edges_updated,
        "findings_created": summary.findings_created,
        "findings_updated_from_new_evidence": summary.findings_updated_from_new_evidence,
        "findings_updated_from_clock_recalculation": summary.findings_updated_from_clock_recalculation,
        "proposals_created": summary.link_proposals_created
        + summary.merge_proposals_created
        + summary.findings_proposed,
        "skipped_low_confidence": summary.skipped_low_confidence,
        "errors": summary.errors,
    }


async def _stamp_source_run_requests(
    session: AsyncSession,
    *,
    source_run_ids: set[str],
    summary: EvidencePipelineSummary,
) -> None:
    if not source_run_ids:
        return
    rows = (
        await session.execute(
            select(SourceRunRequest).where(SourceRunRequest.run_id.in_(list(source_run_ids)))
        )
    ).scalars()
    compact = _compact_source_run_summary(summary)
    for row in rows:
        result = dict(row.result_summary or {})
        previous = result.get("evidence_pipeline")
        if isinstance(previous, dict):
            merged = dict(compact)
            for key in (
                "graph_nodes_created",
                "graph_nodes_updated",
                "graph_edges_created",
                "graph_edges_updated",
                "findings_created",
                "findings_updated_from_new_evidence",
                "findings_updated_from_clock_recalculation",
                "proposals_created",
                "skipped_low_confidence",
                "errors",
            ):
                merged[key] = int(previous.get(key) or 0) + int(compact.get(key) or 0)
            compact_for_row = merged
        else:
            compact_for_row = compact
        if previous == compact_for_row:
            continue
        result["evidence_pipeline"] = compact_for_row
        result["graph_updates"] = (
            compact_for_row["graph_nodes_created"]
            + compact_for_row["graph_edges_created"]
        )
        result["findings_generated"] = compact_for_row["findings_created"]
        result["proposals_generated"] = compact_for_row["proposals_created"]
        row.result_summary = sanitize_for_logs(result)
    await session.flush()


async def run_evidence_pipeline(
    session: AsyncSession,
    *,
    limit: int = 200,
    activity_item_ids: list[str] | None = None,
    run_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    started = now or _now()
    active_run_id = run_id or f"evidence_pipeline_{uuid4().hex}"
    summary = EvidencePipelineSummary(
        run_started_at=started.isoformat(),
        run_id=active_run_id,
        correlation_id=active_run_id,
    )
    previous_run_id = get_run_id()
    set_run_id(active_run_id)
    try:
        query = (
            select(NormalizedActivityItemRecord)
            .order_by(NormalizedActivityItemRecord.id.asc())
            .limit(max(1, min(int(limit), 1000)))
        )
        if activity_item_ids:
            query = (
                select(NormalizedActivityItemRecord)
                .where(NormalizedActivityItemRecord.activity_item_id.in_(activity_item_ids))
                .order_by(NormalizedActivityItemRecord.id.asc())
            )
        items = list(
            (
                await session.execute(query)
            ).scalars()
        )
        summary.normalized_events_seen = len(items)
        source_run_ids: set[str] = set()
        for item in items:
            try:
                source_event = await _source_event_for_item(session, item)
                srid = _source_run_id(item, source_event)
                if srid:
                    source_run_ids.add(srid)
                    if srid not in summary.source_run_ids:
                        summary.source_run_ids.append(srid)
                counts = await lift_normalized_activity_item(session, item)
                _add_item_counts(summary, counts)
                if counts.get("processed"):
                    summary.processed_activity_item_ids.append(item.activity_item_id)
            except Exception as exc:  # noqa: BLE001 - one bad row must not stop pipeline.
                summary.errors += 1
                summary.error_summaries.append(
                    {
                        "activity_item_id": item.activity_item_id,
                        "error_type": type(exc).__name__,
                        "message": "evidence graph lift failed",
                    }
                )
        summary.merge_proposals_created += await suggest_person_merges(session)
        await _stamp_source_run_requests(
            session,
            source_run_ids=source_run_ids,
            summary=summary,
        )
        summary.run_finished_at = _now().isoformat()
        details = sanitize_for_logs(summary.to_dict())
        session.add(
            AgentRunLog(
                run_id=active_run_id,
                agent=AGENT_NAME,
                agent_version=AGENT_VERSION,
                run_started_at=started,
                run_finished_at=_now(),
                input_watermark=str(summary.normalized_events_seen),
                created=(
                    summary.graph_nodes_created
                    + summary.graph_edges_created
                    + summary.findings_created
                    + summary.link_proposals_created
                    + summary.merge_proposals_created
                ),
                updated_from_new_evidence=(
                    summary.graph_nodes_updated
                    + summary.graph_edges_updated
                    + summary.findings_updated_from_new_evidence
                ),
                updated_from_clock_recalculation=summary.findings_updated_from_clock_recalculation,
                unchanged=summary.unchanged,
                auto_resolved=summary.findings_auto_resolved,
                skipped=(
                    summary.skipped_low_confidence
                    + summary.skipped_no_evidence
                    + summary.skipped_archived
                ),
                errors=summary.errors,
                details=details,
            )
        )
        session.add(
            AuditLog(
                event_type="evidence_pipeline_run_finished",
                actor="operator",
                correlation_id=active_run_id,
                trace_id=active_run_id,
                before_ref="normalized_activity_items",
                after_ref=f"agent_run:{active_run_id}",
                payload={
                    "run_id": active_run_id,
                    "external_side_effect": False,
                    "summary": details,
                },
            )
        )
        await session.flush()
        return summary.to_dict()
    finally:
        set_run_id(previous_run_id)
