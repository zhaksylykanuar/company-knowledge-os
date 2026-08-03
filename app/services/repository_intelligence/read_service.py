"""Bounded, workspace-scoped read models for Repository Intelligence (RI-007).

The projection reads only the durable RI-006 PostgreSQL tables and canonical
repository/evidence rows. It performs no provider call, repository checkout,
target execution, external write, or LLM operation. Evidence quotes, source
record payloads, and artifact storage references are intentionally omitted.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import EvidenceRef, Repository
from app.db.repository_intelligence_models import (
    REPOSITORY_CLAIM_STATUS_INFERRED,
    REPOSITORY_FINDING_STATUS_NEW,
    REPOSITORY_FINDING_STATUS_OPEN,
    REPOSITORY_FINDING_STATUS_REGRESSED,
    REPOSITORY_HUMAN_RESOLUTION_PENDING,
    REPOSITORY_LIFECYCLE_STATUS_CURRENT,
    REPOSITORY_LIFECYCLE_STATUS_STALE,
    RepositoryAuditFinding,
    RepositoryAuditRun,
    RepositoryContradiction,
    RepositoryEvidenceLink,
    RepositoryFact,
    RepositoryRelationshipRecord,
)
from app.services.headquarters_read_service import (
    sanitize_headquarters_evidence_url,
)


REPOSITORY_INTELLIGENCE_READ_MODE = "repository_intelligence_read_only"
REPOSITORY_INTELLIGENCE_READ_SOURCE = "ri_006_persistence"

DEFAULT_PORTFOLIO_LIMIT = 100
MAX_PORTFOLIO_LIMIT = 200
DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 50
MAX_DETAIL_FACTS = 100
MAX_DETAIL_RELATIONSHIPS = 100
MAX_DETAIL_FINDINGS = 100
MAX_DETAIL_CONTRADICTIONS = 50
MAX_GRAPH_EDGES = 500
MAX_EVIDENCE_PER_ITEM = 20

_OPEN_FINDING_STATUSES = frozenset(
    {
        REPOSITORY_FINDING_STATUS_NEW,
        REPOSITORY_FINDING_STATUS_OPEN,
        REPOSITORY_FINDING_STATUS_REGRESSED,
    }
)
_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


async def build_repository_intelligence_portfolio(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    limit: int = DEFAULT_PORTFOLIO_LIMIT,
) -> dict[str, Any]:
    """Build the bounded repository portfolio from canonical and RI-006 rows."""

    bounded_limit = _bounded_limit(limit, maximum=MAX_PORTFOLIO_LIMIT)
    repository_rows = list(
        (
            await session.execute(
                select(Repository)
                .where(Repository.workspace_id == workspace_id)
                .order_by(
                    Repository.archived.asc(),
                    Repository.full_name.asc(),
                    Repository.id.asc(),
                )
                .limit(bounded_limit + 1)
            )
        ).scalars()
    )
    truncated = len(repository_rows) > bounded_limit
    repositories = repository_rows[:bounded_limit]
    repository_ids = [repository.id for repository in repositories]

    if not repository_ids:
        return _empty_portfolio(workspace_id=workspace_id, limit=bounded_limit)

    latest_runs = await _latest_runs(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    selected_facts = await _portfolio_facts(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    finding_counts = await _portfolio_finding_counts(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    unknown_counts = await _portfolio_unknown_counts(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    outbound_counts, inbound_counts = await _portfolio_relationship_counts(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    stale_repository_ids = await _stale_repository_ids(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    pending_confirmation_counts = await _pending_confirmation_counts(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )

    items = [
        _portfolio_repository_payload(
            repository=repository,
            latest_run=latest_runs.get(repository.id),
            facts=selected_facts.get(repository.id, []),
            finding_counts=finding_counts.get(repository.id, {}),
            unknown_count=unknown_counts.get(repository.id, 0),
            outbound_count=outbound_counts.get(repository.id, 0),
            inbound_count=inbound_counts.get(repository.id, 0),
            has_stale_intelligence=repository.id in stale_repository_ids,
            pending_confirmation_count=pending_confirmation_counts.get(
                repository.id, 0
            ),
        )
        for repository in repositories
    ]

    return {
        "workspace_id": workspace_id,
        "mode": REPOSITORY_INTELLIGENCE_READ_MODE,
        "source": REPOSITORY_INTELLIGENCE_READ_SOURCE,
        "summary": {
            "repositories": len(items),
            "analyzed_repositories": sum(
                1 for item in items if item["latest_audit"] is not None
            ),
            "repositories_with_open_findings": sum(
                1 for item in items if item["open_findings_total"] > 0
            ),
            "repositories_with_stale_intelligence": sum(
                1 for item in items if item["has_stale_intelligence"]
            ),
            "current_relationships": sum(
                item["outbound_relationship_count"] for item in items
            ),
            "blocking_unknowns": sum(item["unknown_count"] for item in items),
            "pending_confirmations": sum(
                item["pending_confirmation_count"] for item in items
            ),
        },
        "repositories": items,
        "limits": {
            "repositories": bounded_limit,
        },
        "truncated": truncated,
        "capabilities": _read_capabilities(),
        "warnings": (
            []
            if items
            else ["No canonical repositories are available in this workspace."]
        ),
    }


async def build_repository_intelligence_detail(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_id: UUID,
) -> dict[str, Any] | None:
    """Build one repository detail projection with bounded evidence."""

    repository = await _repository(
        session=session,
        workspace_id=workspace_id,
        repository_id=repository_id,
    )
    if repository is None:
        return None

    latest_run = (
        await session.execute(
            select(RepositoryAuditRun)
            .where(
                RepositoryAuditRun.workspace_id == workspace_id,
                RepositoryAuditRun.repository_id == repository_id,
            )
            .order_by(
                RepositoryAuditRun.completed_at.desc(),
                RepositoryAuditRun.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    facts = list(
        (
            await session.execute(
                select(RepositoryFact)
                .where(
                    RepositoryFact.workspace_id == workspace_id,
                    RepositoryFact.repository_id == repository_id,
                )
                .order_by(
                    case(
                        (
                            RepositoryFact.lifecycle_status
                            == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                            0,
                        ),
                        else_=1,
                    ),
                    RepositoryFact.fact_type.asc(),
                    RepositoryFact.updated_at.desc(),
                    RepositoryFact.id.asc(),
                )
                .limit(MAX_DETAIL_FACTS + 1)
            )
        ).scalars()
    )
    relationships = list(
        (
            await session.execute(
                select(RepositoryRelationshipRecord)
                .where(
                    RepositoryRelationshipRecord.workspace_id == workspace_id,
                    or_(
                        RepositoryRelationshipRecord.from_repository_id
                        == repository_id,
                        RepositoryRelationshipRecord.to_repository_id
                        == repository_id,
                    ),
                )
                .order_by(
                    case(
                        (
                            RepositoryRelationshipRecord.lifecycle_status
                            == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                            0,
                        ),
                        else_=1,
                    ),
                    RepositoryRelationshipRecord.updated_at.desc(),
                    RepositoryRelationshipRecord.id.asc(),
                )
                .limit(MAX_DETAIL_RELATIONSHIPS + 1)
            )
        ).scalars()
    )
    findings = list(
        (
            await session.execute(
                select(RepositoryAuditFinding)
                .where(
                    RepositoryAuditFinding.workspace_id == workspace_id,
                    RepositoryAuditFinding.repository_id == repository_id,
                )
                .order_by(
                    case(
                        *[
                            (RepositoryAuditFinding.severity == severity, order)
                            for severity, order in _SEVERITY_ORDER.items()
                        ],
                        else_=len(_SEVERITY_ORDER),
                    ),
                    RepositoryAuditFinding.updated_at.desc(),
                    RepositoryAuditFinding.id.asc(),
                )
                .limit(MAX_DETAIL_FINDINGS + 1)
            )
        ).scalars()
    )
    contradictions = list(
        (
            await session.execute(
                select(RepositoryContradiction)
                .where(
                    RepositoryContradiction.workspace_id == workspace_id,
                    RepositoryContradiction.repository_id == repository_id,
                )
                .order_by(
                    case(
                        (RepositoryContradiction.status == "current", 0),
                        else_=1,
                    ),
                    RepositoryContradiction.updated_at.desc(),
                    RepositoryContradiction.id.asc(),
                )
                .limit(MAX_DETAIL_CONTRADICTIONS + 1)
            )
        ).scalars()
    )

    selected_facts = facts[:MAX_DETAIL_FACTS]
    selected_relationships = relationships[:MAX_DETAIL_RELATIONSHIPS]
    selected_findings = findings[:MAX_DETAIL_FINDINGS]
    selected_contradictions = contradictions[:MAX_DETAIL_CONTRADICTIONS]

    repository_ids = {
        repository_id,
        *(
            relationship.from_repository_id
            for relationship in selected_relationships
        ),
        *(
            relationship.to_repository_id
            for relationship in selected_relationships
            if relationship.to_repository_id is not None
        ),
    }
    repository_names = await _repository_names(
        session=session,
        workspace_id=workspace_id,
        repository_ids=repository_ids,
    )
    run_ids = {
        *(
            run_id
            for fact in selected_facts
            for run_id in (fact.first_seen_run_id, fact.last_seen_run_id)
        ),
        *(
            run_id
            for relationship in selected_relationships
            for run_id in (
                relationship.first_seen_run_id,
                relationship.last_seen_run_id,
            )
        ),
        *(
            run_id
            for finding in selected_findings
            for run_id in (finding.first_seen_run_id, finding.last_seen_run_id)
        ),
        *(
            run_id
            for contradiction in selected_contradictions
            for run_id in (
                contradiction.first_seen_run_id,
                contradiction.last_seen_run_id,
            )
        ),
    }
    run_times = await _run_times(
        session=session,
        workspace_id=workspace_id,
        run_ids=run_ids,
    )
    evidence = await _evidence_by_parent(
        session=session,
        workspace_id=workspace_id,
        fact_ids=[fact.id for fact in selected_facts],
        relationship_ids=[
            relationship.id for relationship in selected_relationships
        ],
        finding_ids=[finding.id for finding in selected_findings],
        contradiction_ids=[
            contradiction.id for contradiction in selected_contradictions
        ],
    )

    fact_rows = [
        _fact_payload(
            fact,
            evidence=evidence.get(("fact", fact.id), []),
            run_times=run_times,
        )
        for fact in selected_facts
    ]
    relationship_rows = [
        _relationship_payload(
            relationship,
            selected_repository_id=repository_id,
            repository_names=repository_names,
            evidence=evidence.get(("relationship", relationship.id), []),
            run_times=run_times,
        )
        for relationship in selected_relationships
    ]
    finding_rows = [
        _finding_payload(
            finding,
            evidence=evidence.get(("finding", finding.id), []),
            run_times=run_times,
        )
        for finding in selected_findings
    ]
    contradiction_rows = [
        _contradiction_payload(
            contradiction,
            facts_by_id={fact.id: fact for fact in selected_facts},
            evidence=evidence.get(("contradiction", contradiction.id), []),
            run_times=run_times,
        )
        for contradiction in selected_contradictions
    ]
    unknowns = [
        fact for fact in fact_rows if fact["fact_type"] == "unknown"
    ]
    confirmation_queue = [
        {
            "kind": "fact",
            "id": fact["id"],
            "label": _fact_label(fact),
            "claim_status": fact["claim_status"],
            "human_resolution_status": fact["human_resolution_status"],
            "evidence": fact["evidence"],
        }
        for fact in fact_rows
        if _fact_requires_confirmation_payload(fact)
    ]
    confirmation_queue.extend(
        {
            "kind": "relationship",
            "id": relationship["id"],
            "label": relationship["summary"]
            or (
                f"{relationship['from_repository']['full_name']} "
                f"{relationship['relationship_type']} "
                f"{relationship['target_full_name']}"
            ),
            "claim_status": relationship["claim_status"],
            "human_resolution_status": relationship[
                "human_resolution_status"
            ],
            "evidence": relationship["evidence"],
        }
        for relationship in relationship_rows
        if _relationship_requires_confirmation_payload(relationship)
    )

    purpose = next(
        (
            fact
            for fact in fact_rows
            if fact["fact_type"] == "purpose"
            and fact["lifecycle_status"] == REPOSITORY_LIFECYCLE_STATUS_CURRENT
        ),
        None,
    )

    return {
        "workspace_id": workspace_id,
        "mode": REPOSITORY_INTELLIGENCE_READ_MODE,
        "source": REPOSITORY_INTELLIGENCE_READ_SOURCE,
        "repository": _repository_identity_payload(repository),
        "purpose": purpose,
        "latest_audit": _latest_audit_payload(latest_run),
        "facts": fact_rows,
        "relationships": relationship_rows,
        "findings": finding_rows,
        "contradictions": contradiction_rows,
        "unknowns": unknowns,
        "confirmation_queue": confirmation_queue[:100],
        "limitations": (
            _safe_string_list(latest_run.limitations, limit=50)
            if latest_run is not None
            else []
        ),
        "truncated": {
            "facts": len(facts) > MAX_DETAIL_FACTS,
            "relationships": len(relationships) > MAX_DETAIL_RELATIONSHIPS,
            "findings": len(findings) > MAX_DETAIL_FINDINGS,
            "contradictions": len(contradictions)
            > MAX_DETAIL_CONTRADICTIONS,
            "confirmation_queue": len(confirmation_queue) > 100,
        },
        "capabilities": _read_capabilities(),
    }


async def build_repository_intelligence_history(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_id: UUID,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any] | None:
    """Return bounded immutable audit-run headers without artifact paths."""

    repository = await _repository(
        session=session,
        workspace_id=workspace_id,
        repository_id=repository_id,
    )
    if repository is None:
        return None
    bounded_limit = _bounded_limit(limit, maximum=MAX_HISTORY_LIMIT)
    runs = list(
        (
            await session.execute(
                select(RepositoryAuditRun)
                .where(
                    RepositoryAuditRun.workspace_id == workspace_id,
                    RepositoryAuditRun.repository_id == repository_id,
                )
                .order_by(
                    RepositoryAuditRun.completed_at.desc(),
                    RepositoryAuditRun.id.desc(),
                )
                .limit(bounded_limit + 1)
            )
        ).scalars()
    )
    return {
        "workspace_id": workspace_id,
        "mode": REPOSITORY_INTELLIGENCE_READ_MODE,
        "source": REPOSITORY_INTELLIGENCE_READ_SOURCE,
        "repository": _repository_identity_payload(repository),
        "runs": [_history_run_payload(run) for run in runs[:bounded_limit]],
        "limit": bounded_limit,
        "truncated": len(runs) > bounded_limit,
        "capabilities": _read_capabilities(),
    }


async def build_repository_intelligence_graph(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_limit: int = MAX_PORTFOLIO_LIMIT,
    edge_limit: int = MAX_GRAPH_EDGES,
) -> dict[str, Any]:
    """Return the bounded current directional repository graph."""

    portfolio = await build_repository_intelligence_portfolio(
        session=session,
        workspace_id=workspace_id,
        limit=_bounded_limit(
            repository_limit,
            maximum=MAX_PORTFOLIO_LIMIT,
        ),
    )
    node_rows = portfolio["repositories"]
    node_ids = {UUID(str(node["id"])) for node in node_rows}
    bounded_edge_limit = _bounded_limit(edge_limit, maximum=MAX_GRAPH_EDGES)
    relationships = list(
        (
            await session.execute(
                select(RepositoryRelationshipRecord)
                .where(
                    RepositoryRelationshipRecord.workspace_id == workspace_id,
                    RepositoryRelationshipRecord.lifecycle_status
                    == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                    RepositoryRelationshipRecord.from_repository_id.in_(
                        node_ids or {UUID(int=0)}
                    ),
                )
                .order_by(
                    RepositoryRelationshipRecord.from_repository_id.asc(),
                    RepositoryRelationshipRecord.relationship_type.asc(),
                    RepositoryRelationshipRecord.target_full_name.asc(),
                    RepositoryRelationshipRecord.id.asc(),
                )
                .limit(bounded_edge_limit + 1)
            )
        ).scalars()
    )
    selected_edges = relationships[:bounded_edge_limit]
    names = {
        UUID(str(node["id"])): str(node["full_name"]) for node in node_rows
    }
    edge_rows = [
        {
            "id": relationship.id,
            "from_repository_id": relationship.from_repository_id,
            "from_repository_full_name": names.get(
                relationship.from_repository_id, "unknown"
            ),
            "to_repository_id": relationship.to_repository_id,
            "target_full_name": relationship.target_full_name,
            "relationship_type": relationship.relationship_type,
            "resolution_status": relationship.resolution_status,
            "claim_status": relationship.claim_status,
            "human_resolution_status": relationship.human_resolution_status,
            "confidence": relationship.confidence,
            "summary": _safe_optional_text(relationship.summary, limit=1000),
        }
        for relationship in selected_edges
    ]
    return {
        "workspace_id": workspace_id,
        "mode": REPOSITORY_INTELLIGENCE_READ_MODE,
        "source": REPOSITORY_INTELLIGENCE_READ_SOURCE,
        "nodes": [
            {
                "id": node["id"],
                "full_name": node["full_name"],
                "repository_type": node["repository_type"],
                "archived": node["archived"],
                "open_findings_total": node["open_findings_total"],
                "has_stale_intelligence": node["has_stale_intelligence"],
                "latest_audit_at": (
                    node["latest_audit"]["completed_at"]
                    if node["latest_audit"] is not None
                    else None
                ),
            }
            for node in node_rows
        ],
        "edges": edge_rows,
        "summary": {
            "nodes": len(node_rows),
            "edges": len(edge_rows),
            "observed_edges": sum(
                1 for edge in edge_rows if edge["claim_status"] == "observed"
            ),
            "inferred_edges": sum(
                1 for edge in edge_rows if edge["claim_status"] == "inferred"
            ),
            "candidate_edges": sum(
                1
                for edge in edge_rows
                if edge["resolution_status"] == "candidate"
            ),
        },
        "truncated": {
            "nodes": bool(portfolio["truncated"]),
            "edges": len(relationships) > bounded_edge_limit,
        },
        "capabilities": _read_capabilities(),
    }


async def _repository(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_id: UUID,
) -> Repository | None:
    return await session.scalar(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.id == repository_id,
        )
    )


async def _latest_runs(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> dict[UUID, RepositoryAuditRun]:
    if not repository_ids:
        return {}
    rows = (
        await session.execute(
            select(RepositoryAuditRun)
            .where(
                RepositoryAuditRun.workspace_id == workspace_id,
                RepositoryAuditRun.repository_id.in_(repository_ids),
            )
            .order_by(
                RepositoryAuditRun.repository_id.asc(),
                RepositoryAuditRun.completed_at.desc(),
                RepositoryAuditRun.id.desc(),
            )
            .distinct(RepositoryAuditRun.repository_id)
        )
    ).scalars()
    return {run.repository_id: run for run in rows}


async def _portfolio_facts(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> dict[UUID, list[RepositoryFact]]:
    rows = (
        await session.execute(
            select(RepositoryFact)
            .where(
                RepositoryFact.workspace_id == workspace_id,
                RepositoryFact.repository_id.in_(repository_ids),
                RepositoryFact.lifecycle_status
                == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                RepositoryFact.fact_type.in_(
                    ("purpose", "owner_candidate", "product_candidate")
                ),
            )
            .order_by(
                RepositoryFact.repository_id.asc(),
                RepositoryFact.fact_type.asc(),
                RepositoryFact.updated_at.desc(),
                RepositoryFact.id.asc(),
            )
        )
    ).scalars()
    result: dict[UUID, list[RepositoryFact]] = defaultdict(list)
    for row in rows:
        result[row.repository_id].append(row)
    return dict(result)


async def _portfolio_finding_counts(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> dict[UUID, dict[str, int]]:
    rows = (
        await session.execute(
            select(
                RepositoryAuditFinding.repository_id,
                RepositoryAuditFinding.severity,
                func.count(RepositoryAuditFinding.id),
            )
            .where(
                RepositoryAuditFinding.workspace_id == workspace_id,
                RepositoryAuditFinding.repository_id.in_(repository_ids),
                RepositoryAuditFinding.status.in_(_OPEN_FINDING_STATUSES),
            )
            .group_by(
                RepositoryAuditFinding.repository_id,
                RepositoryAuditFinding.severity,
            )
        )
    ).all()
    result: dict[UUID, dict[str, int]] = defaultdict(dict)
    for repository_id, severity, count in rows:
        result[repository_id][severity] = int(count or 0)
    return dict(result)


async def _portfolio_unknown_counts(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> dict[UUID, int]:
    rows = (
        await session.execute(
            select(
                RepositoryFact.repository_id,
                func.count(RepositoryFact.id),
            )
            .where(
                RepositoryFact.workspace_id == workspace_id,
                RepositoryFact.repository_id.in_(repository_ids),
                RepositoryFact.fact_type == "unknown",
                RepositoryFact.lifecycle_status
                == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
            )
            .group_by(RepositoryFact.repository_id)
        )
    ).all()
    return {repository_id: int(count or 0) for repository_id, count in rows}


async def _portfolio_relationship_counts(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> tuple[dict[UUID, int], dict[UUID, int]]:
    outbound_rows = (
        await session.execute(
            select(
                RepositoryRelationshipRecord.from_repository_id,
                func.count(RepositoryRelationshipRecord.id),
            )
            .where(
                RepositoryRelationshipRecord.workspace_id == workspace_id,
                RepositoryRelationshipRecord.from_repository_id.in_(
                    repository_ids
                ),
                RepositoryRelationshipRecord.lifecycle_status
                == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
            )
            .group_by(RepositoryRelationshipRecord.from_repository_id)
        )
    ).all()
    inbound_rows = (
        await session.execute(
            select(
                RepositoryRelationshipRecord.to_repository_id,
                func.count(RepositoryRelationshipRecord.id),
            )
            .where(
                RepositoryRelationshipRecord.workspace_id == workspace_id,
                RepositoryRelationshipRecord.to_repository_id.in_(
                    repository_ids
                ),
                RepositoryRelationshipRecord.lifecycle_status
                == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
            )
            .group_by(RepositoryRelationshipRecord.to_repository_id)
        )
    ).all()
    return (
        {
            repository_id: int(count or 0)
            for repository_id, count in outbound_rows
        },
        {
            repository_id: int(count or 0)
            for repository_id, count in inbound_rows
            if repository_id is not None
        },
    )


async def _stale_repository_ids(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> set[UUID]:
    fact_ids = set(
        (
            await session.execute(
                select(RepositoryFact.repository_id)
                .where(
                    RepositoryFact.workspace_id == workspace_id,
                    RepositoryFact.repository_id.in_(repository_ids),
                    RepositoryFact.lifecycle_status
                    == REPOSITORY_LIFECYCLE_STATUS_STALE,
                )
                .distinct()
            )
        ).scalars()
    )
    relationship_ids = set(
        (
            await session.execute(
                select(RepositoryRelationshipRecord.from_repository_id)
                .where(
                    RepositoryRelationshipRecord.workspace_id == workspace_id,
                    RepositoryRelationshipRecord.from_repository_id.in_(
                        repository_ids
                    ),
                    RepositoryRelationshipRecord.lifecycle_status
                    == REPOSITORY_LIFECYCLE_STATUS_STALE,
                )
                .distinct()
            )
        ).scalars()
    )
    return fact_ids | relationship_ids


async def _pending_confirmation_counts(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Sequence[UUID],
) -> dict[UUID, int]:
    fact_rows = (
        await session.execute(
            select(
                RepositoryFact.repository_id,
                func.count(RepositoryFact.id),
            )
            .where(
                RepositoryFact.workspace_id == workspace_id,
                RepositoryFact.repository_id.in_(repository_ids),
                RepositoryFact.lifecycle_status
                == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                RepositoryFact.human_resolution_status
                == REPOSITORY_HUMAN_RESOLUTION_PENDING,
                or_(
                    RepositoryFact.claim_status
                    == REPOSITORY_CLAIM_STATUS_INFERRED,
                    RepositoryFact.fact_type.in_(
                        ("owner_candidate", "product_candidate")
                    ),
                ),
            )
            .group_by(RepositoryFact.repository_id)
        )
    ).all()
    relationship_rows = (
        await session.execute(
            select(
                RepositoryRelationshipRecord.from_repository_id,
                func.count(RepositoryRelationshipRecord.id),
            )
            .where(
                RepositoryRelationshipRecord.workspace_id == workspace_id,
                RepositoryRelationshipRecord.from_repository_id.in_(
                    repository_ids
                ),
                RepositoryRelationshipRecord.lifecycle_status
                == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                RepositoryRelationshipRecord.human_resolution_status
                == REPOSITORY_HUMAN_RESOLUTION_PENDING,
                or_(
                    RepositoryRelationshipRecord.claim_status
                    == REPOSITORY_CLAIM_STATUS_INFERRED,
                    RepositoryRelationshipRecord.resolution_status
                    == "candidate",
                ),
            )
            .group_by(RepositoryRelationshipRecord.from_repository_id)
        )
    ).all()
    counts: dict[UUID, int] = defaultdict(int)
    for repository_id, count in [*fact_rows, *relationship_rows]:
        counts[repository_id] += int(count or 0)
    return dict(counts)


async def _repository_names(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository_ids: Iterable[UUID],
) -> dict[UUID, str]:
    selected = list(set(repository_ids))
    if not selected:
        return {}
    rows = (
        await session.execute(
            select(Repository.id, Repository.full_name).where(
                Repository.workspace_id == workspace_id,
                Repository.id.in_(selected),
            )
        )
    ).all()
    return {repository_id: full_name for repository_id, full_name in rows}


async def _run_times(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    run_ids: Iterable[UUID],
) -> dict[UUID, datetime]:
    selected = list(set(run_ids))
    if not selected:
        return {}
    rows = (
        await session.execute(
            select(RepositoryAuditRun.id, RepositoryAuditRun.completed_at).where(
                RepositoryAuditRun.workspace_id == workspace_id,
                RepositoryAuditRun.id.in_(selected),
            )
        )
    ).all()
    return {run_id: completed_at for run_id, completed_at in rows}


async def _evidence_by_parent(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    fact_ids: Sequence[UUID],
    relationship_ids: Sequence[UUID],
    finding_ids: Sequence[UUID],
    contradiction_ids: Sequence[UUID],
) -> dict[tuple[str, UUID], list[dict[str, Any]]]:
    parent_filters = []
    if fact_ids:
        parent_filters.append(RepositoryEvidenceLink.fact_id.in_(fact_ids))
    if relationship_ids:
        parent_filters.append(
            RepositoryEvidenceLink.relationship_id.in_(relationship_ids)
        )
    if finding_ids:
        parent_filters.append(RepositoryEvidenceLink.finding_id.in_(finding_ids))
    if contradiction_ids:
        parent_filters.append(
            RepositoryEvidenceLink.contradiction_id.in_(contradiction_ids)
        )
    if not parent_filters:
        return {}
    rows = (
        await session.execute(
            select(RepositoryEvidenceLink, EvidenceRef)
            .join(
                EvidenceRef,
                and_(
                    EvidenceRef.workspace_id
                    == RepositoryEvidenceLink.workspace_id,
                    EvidenceRef.id == RepositoryEvidenceLink.evidence_ref_id,
                ),
            )
            .where(
                RepositoryEvidenceLink.workspace_id == workspace_id,
                or_(*parent_filters),
            )
            .order_by(
                RepositoryEvidenceLink.created_at.asc(),
                RepositoryEvidenceLink.id.asc(),
            )
        )
    ).all()
    result: dict[tuple[str, UUID], list[dict[str, Any]]] = defaultdict(list)
    for link, evidence_ref in rows:
        parent = _evidence_parent(link)
        if parent is None or len(result[parent]) >= MAX_EVIDENCE_PER_ITEM:
            continue
        result[parent].append(_evidence_payload(link, evidence_ref))
    return dict(result)


def _evidence_parent(
    link: RepositoryEvidenceLink,
) -> tuple[str, UUID] | None:
    for name, value in (
        ("fact", link.fact_id),
        ("relationship", link.relationship_id),
        ("finding", link.finding_id),
        ("contradiction", link.contradiction_id),
    ):
        if value is not None:
            return name, value
    return None


def _portfolio_repository_payload(
    *,
    repository: Repository,
    latest_run: RepositoryAuditRun | None,
    facts: Sequence[RepositoryFact],
    finding_counts: Mapping[str, int],
    unknown_count: int,
    outbound_count: int,
    inbound_count: int,
    has_stale_intelligence: bool,
    pending_confirmation_count: int,
) -> dict[str, Any]:
    purpose = next((fact for fact in facts if fact.fact_type == "purpose"), None)
    owner_candidates = [
        _claim_summary(fact)
        for fact in facts
        if fact.fact_type == "owner_candidate" and _claim_summary(fact)
    ][:20]
    product_candidates = [
        _claim_summary(fact)
        for fact in facts
        if fact.fact_type == "product_candidate" and _claim_summary(fact)
    ][:20]
    purpose_value = (
        purpose.value if purpose is not None and isinstance(purpose.value, Mapping) else {}
    )
    open_findings = {
        severity: int(finding_counts.get(severity, 0))
        for severity in ("critical", "high", "medium", "low", "info")
    }
    return {
        **_repository_identity_payload(repository),
        "purpose_summary": _safe_optional_text(
            purpose_value.get("summary"), limit=1000
        ),
        "operational_summary": _safe_optional_text(
            purpose_value.get("operational_summary"), limit=2000
        ),
        "repository_type": _safe_optional_text(
            purpose_value.get("repository_type"), limit=80
        )
        or "unknown",
        "purpose_status": purpose.claim_status if purpose is not None else "unavailable",
        "purpose_confidence": purpose.confidence if purpose is not None else 0.0,
        "product_candidates": product_candidates,
        "owner_candidates": owner_candidates,
        "has_confirmed_owner": any(
            fact.fact_type == "owner_candidate"
            and fact.human_resolution_status == "confirmed"
            for fact in facts
        ),
        "latest_audit": _latest_audit_payload(latest_run),
        "open_findings": open_findings,
        "open_findings_total": sum(open_findings.values()),
        "outbound_relationship_count": outbound_count,
        "inbound_relationship_count": inbound_count,
        "unknown_count": unknown_count,
        "pending_confirmation_count": pending_confirmation_count,
        "has_stale_intelligence": has_stale_intelligence,
    }


def _repository_identity_payload(repository: Repository) -> dict[str, Any]:
    return {
        "id": repository.id,
        "provider": repository.provider,
        "external_id": repository.external_id,
        "name": repository.name,
        "full_name": repository.full_name,
        "default_branch": repository.default_branch,
        "visibility": repository.visibility,
        "archived": repository.archived,
        "source_url": sanitize_headquarters_evidence_url(repository.source_url),
        "last_activity_at": repository.last_activity_at,
    }


def _latest_audit_payload(run: RepositoryAuditRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "audit_level": run.audit_level,
        "target_status": run.target_status,
        "commit_sha": run.commit_sha,
        "metadata_snapshot_id": run.metadata_snapshot_id,
        "profile": run.profile,
        "engine_version": run.engine_version,
        "status": run.status,
        "coverage_status": run.coverage_status,
        "reconciliation_applied": run.reconciliation_applied,
        "completed_at": run.completed_at,
        "artifact_status": (
            "purged" if run.artifact_purged_at is not None else "retained"
        ),
    }


def _fact_payload(
    fact: RepositoryFact,
    *,
    evidence: list[dict[str, Any]],
    run_times: Mapping[UUID, datetime],
) -> dict[str, Any]:
    return {
        "id": fact.id,
        "fact_type": fact.fact_type,
        "claim_id": fact.claim_id,
        "value": _fact_value(fact.fact_type, fact.value),
        "claim_status": fact.claim_status,
        "confidence": fact.confidence,
        "lifecycle_status": fact.lifecycle_status,
        "human_resolution_status": fact.human_resolution_status,
        "first_seen_at": run_times.get(fact.first_seen_run_id),
        "last_seen_at": run_times.get(fact.last_seen_run_id),
        "stale_at": fact.stale_at,
        "evidence": evidence,
    }


def _relationship_payload(
    relationship: RepositoryRelationshipRecord,
    *,
    selected_repository_id: UUID,
    repository_names: Mapping[UUID, str],
    evidence: list[dict[str, Any]],
    run_times: Mapping[UUID, datetime],
) -> dict[str, Any]:
    direction: Literal["outbound", "inbound"] = (
        "outbound"
        if relationship.from_repository_id == selected_repository_id
        else "inbound"
    )
    return {
        "id": relationship.id,
        "direction": direction,
        "from_repository": {
            "id": relationship.from_repository_id,
            "full_name": repository_names.get(
                relationship.from_repository_id, "unknown"
            ),
        },
        "to_repository": (
            {
                "id": relationship.to_repository_id,
                "full_name": repository_names.get(
                    relationship.to_repository_id,
                    relationship.target_full_name,
                ),
            }
            if relationship.to_repository_id is not None
            else None
        ),
        "target_full_name": relationship.target_full_name,
        "relationship_type": relationship.relationship_type,
        "resolution_status": relationship.resolution_status,
        "summary": _safe_optional_text(relationship.summary, limit=1000),
        "claim_status": relationship.claim_status,
        "confidence": relationship.confidence,
        "lifecycle_status": relationship.lifecycle_status,
        "human_resolution_status": relationship.human_resolution_status,
        "first_seen_at": run_times.get(relationship.first_seen_run_id),
        "last_seen_at": run_times.get(relationship.last_seen_run_id),
        "stale_at": relationship.stale_at,
        "evidence": evidence,
    }


def _finding_payload(
    finding: RepositoryAuditFinding,
    *,
    evidence: list[dict[str, Any]],
    run_times: Mapping[UUID, datetime],
) -> dict[str, Any]:
    return {
        "id": finding.id,
        "finding_id": finding.finding_id,
        "rule_id": finding.rule_id,
        "category": finding.category,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status,
        "title": finding.title,
        "summary": finding.summary,
        "recommended_next_step": finding.recommended_next_step,
        "first_seen_at": run_times.get(finding.first_seen_run_id),
        "last_seen_at": run_times.get(finding.last_seen_run_id),
        "resolved_at": finding.resolved_at,
        "evidence": evidence,
    }


def _contradiction_payload(
    contradiction: RepositoryContradiction,
    *,
    facts_by_id: Mapping[UUID, RepositoryFact],
    evidence: list[dict[str, Any]],
    run_times: Mapping[UUID, datetime],
) -> dict[str, Any]:
    left = facts_by_id.get(contradiction.left_fact_id)
    right = facts_by_id.get(contradiction.right_fact_id)
    return {
        "id": contradiction.id,
        "contradiction_id": contradiction.contradiction_id,
        "status": contradiction.status,
        "confidence": contradiction.confidence,
        "summary": contradiction.summary,
        "left_fact": _contradiction_fact_payload(left),
        "right_fact": _contradiction_fact_payload(right),
        "first_seen_at": run_times.get(contradiction.first_seen_run_id),
        "last_seen_at": run_times.get(contradiction.last_seen_run_id),
        "resolved_at": contradiction.resolved_at,
        "evidence": evidence,
    }


def _contradiction_fact_payload(
    fact: RepositoryFact | None,
) -> dict[str, Any] | None:
    if fact is None:
        return None
    return {
        "id": fact.id,
        "fact_type": fact.fact_type,
        "claim_id": fact.claim_id,
        "value": _fact_value(fact.fact_type, fact.value),
        "claim_status": fact.claim_status,
    }


def _history_run_payload(run: RepositoryAuditRun) -> dict[str, Any]:
    coverage = run.coverage if isinstance(run.coverage, Mapping) else {}
    return {
        "id": run.id,
        "audit_level": run.audit_level,
        "target_status": run.target_status,
        "commit_sha": run.commit_sha,
        "metadata_snapshot_id": run.metadata_snapshot_id,
        "profile": run.profile,
        "policy_hash": run.policy_hash,
        "engine_version": run.engine_version,
        "status": run.status,
        "coverage_status": run.coverage_status,
        "completed_checks": _safe_string_list(
            coverage.get("completed_checks"), limit=50
        ),
        "failed_checks": _safe_string_list(
            coverage.get("failed_checks"), limit=50
        ),
        "skipped_checks": _safe_string_list(
            coverage.get("skipped_checks"), limit=50
        ),
        "limitations": _safe_string_list(run.limitations, limit=50),
        "reconciliation_applied": run.reconciliation_applied,
        "artifact_count": len(run.artifact_manifest)
        if isinstance(run.artifact_manifest, list)
        else 0,
        "artifact_status": (
            "purged" if run.artifact_purged_at is not None else "retained"
        ),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def _evidence_payload(
    link: RepositoryEvidenceLink,
    evidence_ref: EvidenceRef,
) -> dict[str, Any]:
    selector = _safe_optional_text(evidence_ref.selector, limit=500)
    return {
        "id": evidence_ref.id,
        "role": link.evidence_role,
        "kind": evidence_ref.evidence_kind or "repository_metadata",
        "source": evidence_ref.evidence_source or "internal",
        "ref": selector,
        "record_id": evidence_ref.source_record_id,
        "url": sanitize_headquarters_evidence_url(evidence_ref.source_url),
        "confidence": evidence_ref.confidence,
    }


def _fact_value(fact_type: str, value: Any) -> dict[str, Any]:
    material = value if isinstance(value, Mapping) else {}
    if fact_type == "purpose":
        return {
            "summary": _safe_optional_text(material.get("summary"), limit=1000),
            "operational_summary": _safe_optional_text(
                material.get("operational_summary"), limit=2000
            ),
            "repository_type": _safe_optional_text(
                material.get("repository_type"), limit=80
            )
            or "unknown",
        }
    if fact_type == "unknown":
        return {
            "question": _safe_optional_text(material.get("question"), limit=1000)
            or "Unknown repository question",
        }
    return {
        "claim_type": _safe_optional_text(material.get("claim_type"), limit=80),
        "summary": _safe_optional_text(material.get("summary"), limit=1000),
        "details": _safe_string_list(material.get("details"), limit=20),
    }


def _fact_requires_confirmation_payload(fact: Mapping[str, Any]) -> bool:
    return (
        fact.get("lifecycle_status") == REPOSITORY_LIFECYCLE_STATUS_CURRENT
        and fact.get("human_resolution_status")
        == REPOSITORY_HUMAN_RESOLUTION_PENDING
        and (
            fact.get("claim_status") == REPOSITORY_CLAIM_STATUS_INFERRED
            or fact.get("fact_type")
            in {"owner_candidate", "product_candidate"}
        )
    )


def _relationship_requires_confirmation_payload(
    relationship: Mapping[str, Any],
) -> bool:
    return (
        relationship.get("lifecycle_status")
        == REPOSITORY_LIFECYCLE_STATUS_CURRENT
        and relationship.get("human_resolution_status")
        == REPOSITORY_HUMAN_RESOLUTION_PENDING
        and (
            relationship.get("claim_status")
            == REPOSITORY_CLAIM_STATUS_INFERRED
            or relationship.get("resolution_status") == "candidate"
        )
    )


def _fact_label(fact: Mapping[str, Any]) -> str:
    value = fact.get("value")
    material = value if isinstance(value, Mapping) else {}
    for key in ("summary", "question", "repository_type"):
        text = _safe_optional_text(material.get(key), limit=1000)
        if text:
            return text
    return str(fact.get("fact_type") or "repository fact")


def _claim_summary(fact: RepositoryFact) -> str | None:
    value = fact.value if isinstance(fact.value, Mapping) else {}
    return _safe_optional_text(value.get("summary"), limit=1000)


def _safe_optional_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if (
        not text
        or len(text) > limit
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        return None
    return text


def _safe_string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:limit]:
        text = _safe_optional_text(item, limit=500)
        if text is not None:
            result.append(text)
    return result


def _bounded_limit(value: int, *, maximum: int) -> int:
    return max(1, min(int(value), maximum))


def _read_capabilities() -> dict[str, bool]:
    return {
        "provider_calls": False,
        "repository_reads": False,
        "target_execution": False,
        "external_writes": False,
        "llm_used": False,
        "human_resolution_writes": False,
    }


def _empty_portfolio(*, workspace_id: UUID, limit: int) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "mode": REPOSITORY_INTELLIGENCE_READ_MODE,
        "source": REPOSITORY_INTELLIGENCE_READ_SOURCE,
        "summary": {
            "repositories": 0,
            "analyzed_repositories": 0,
            "repositories_with_open_findings": 0,
            "repositories_with_stale_intelligence": 0,
            "current_relationships": 0,
            "blocking_unknowns": 0,
            "pending_confirmations": 0,
        },
        "repositories": [],
        "limits": {"repositories": limit},
        "truncated": False,
        "capabilities": _read_capabilities(),
        "warnings": [
            "No canonical repositories are available in this workspace."
        ],
    }
