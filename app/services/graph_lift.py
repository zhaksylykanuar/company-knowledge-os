"""Graph lift agent: project people and extracted knowledge into the graph.

Deterministic, idempotent, evidence-backed:

- people from Jira assignees and GitHub PR/commit authors become
  ``person`` nodes with ``works_on`` links to their projects;
- extracted decisions / risks / tasks become graph nodes; risks and
  tasks get ``affects``/``mentions`` links to projects recognized in
  their titles via the existing alias resolution;
- a Jira person and a GitHub person whose names look alike are NOT
  merged silently — the agent files a merge proposal for the inbox.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityRecord
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.agent_proposals import create_proposal
from app.services.entity_resolution import ENTITY_TYPE_PROJECT, resolve_entities_in_text
from app.services.github_graph_mapping import repos_for_project
from app.services.jira_graph_mapping import jira_keys_for_project
from app.services.knowledge_graph import (
    ENTITY_DECISION,
    ENTITY_PERSON,
    ENTITY_RISK,
    ENTITY_TASK,
    REL_AFFECTS,
    REL_DECIDED_IN,
    REL_MENTIONS,
    REL_WORKS_ON,
    person_entity_id,
    upsert_alias,
    upsert_entity,
    upsert_link,
)
from app.services.project_status_view import load_project_issue_snapshots, load_repo_activity

AGENT_NAME = "graph_lift"
KIND_MERGE_PERSON = "merge_person"

_ = REL_DECIDED_IN  # reserved for the meeting agent slice


async def _load_projects(session: AsyncSession) -> list[EntityRecord]:
    rows = (
        await session.execute(
            select(EntityRecord)
            .where(EntityRecord.entity_type == ENTITY_TYPE_PROJECT)
            .order_by(EntityRecord.canonical_name)
        )
    ).scalars()
    return list(rows)


async def _lift_person(
    session: AsyncSession,
    *,
    display_name: str,
    source: str,
    project_entity_id: str,
    evidence: dict[str, Any],
    counts: dict[str, int],
) -> str | None:
    name = (display_name or "").strip()
    if not name or name.casefold() in {"unassigned", "none", "unknown"}:
        return None
    entity_id = person_entity_id(name)
    created = await upsert_entity(
        session,
        entity_id=entity_id,
        entity_type=ENTITY_PERSON,
        canonical_name=name,
        attrs={f"seen_in_{source}": True},
    )
    if created:
        counts["people_created"] += 1
        await upsert_alias(session, entity_id=entity_id, alias=name, source=source)
    if await upsert_link(
        session,
        from_entity_id=entity_id,
        relation=REL_WORKS_ON,
        to_entity_id=project_entity_id,
        evidence_refs=[evidence],
        confidence=0.9,
    ):
        counts["links_created"] += 1
    return entity_id


async def lift_people(session: AsyncSession, *, now: Any = None) -> dict[str, int]:
    """People from Jira assignees and GitHub authors, linked to projects."""

    counts = {"people_created": 0, "links_created": 0, "merge_proposals": 0}
    jira_people: set[str] = set()
    github_people: set[str] = set()

    for project in await _load_projects(session):
        jira_keys = await jira_keys_for_project(session, project.entity_id)
        for snapshot in await load_project_issue_snapshots(session, jira_keys):
            entity_id = await _lift_person(
                session,
                display_name=snapshot.assignee,
                source="jira",
                project_entity_id=project.entity_id,
                evidence={"kind": "jira_issue", "issue_key": snapshot.issue_key},
                counts=counts,
            )
            if entity_id:
                jira_people.add(entity_id)

        repos = await repos_for_project(session, project.entity_id)
        activity = await load_repo_activity(session, repos, now=now)
        if activity is None:
            continue
        for pr in list(activity.open_prs) + list(activity.merged_prs):
            entity_id = await _lift_person(
                session,
                display_name=pr.author,
                source="github",
                project_entity_id=project.entity_id,
                evidence={"kind": "github_pr", "pr_id": pr.pr_id},
                counts=counts,
            )
            if entity_id:
                github_people.add(entity_id)

    counts["merge_proposals"] = await _propose_person_merges(
        session, jira_people=jira_people, github_people=github_people
    )
    return counts


def _name_tokens(entity_id: str) -> set[str]:
    return {tok for tok in entity_id.split(":", 1)[-1].split("-") if len(tok) > 2}


async def _propose_person_merges(
    session: AsyncSession,
    *,
    jira_people: set[str],
    github_people: set[str],
) -> int:
    """File merge proposals for likely-same people across sources."""

    proposals = 0
    for gh in sorted(github_people - jira_people):
        gh_tokens = _name_tokens(gh)
        if not gh_tokens:
            continue
        for jr in sorted(jira_people - github_people):
            shared = gh_tokens & _name_tokens(jr)
            if not shared:
                continue
            pair = sorted([gh, jr])
            created = await create_proposal(
                session,
                proposal_id=f"merge:{pair[0]}+{pair[1]}",
                agent=AGENT_NAME,
                kind=KIND_MERGE_PERSON,
                title=f"Это один человек? {gh} и {jr}",
                payload={"keep": jr, "merge": gh, "shared_tokens": sorted(shared)},
                evidence_refs=[{"kind": "name_overlap", "tokens": sorted(shared)}],
                confidence=0.6,
            )
            if created:
                proposals += 1
    return proposals


async def _project_links_for_text(
    session: AsyncSession,
    *,
    text: str,
) -> list[str]:
    try:
        resolved = await resolve_entities_in_text(
            session, text, entity_type=ENTITY_TYPE_PROJECT
        )
    except Exception:
        return []
    return [match.entity_id for match in resolved]


async def lift_extracted(session: AsyncSession) -> dict[str, int]:
    """Extracted decisions / risks / tasks become graph nodes with links."""

    counts = {"nodes_created": 0, "links_created": 0}

    specs = [
        (ExtractedDecision, ENTITY_DECISION, REL_MENTIONS),
        (ExtractedRisk, ENTITY_RISK, REL_AFFECTS),
        (ExtractedTask, ENTITY_TASK, REL_MENTIONS),
    ]
    for model, entity_type, project_relation in specs:
        rows = (await session.execute(select(model))).scalars()
        for row in rows:
            entity_id = f"{entity_type}:{row.id}"
            attrs = {
                "source_document_id": row.source_document_id,
                "chunk_id": row.chunk_id,
                "confidence": row.confidence,
            }
            if entity_type == ENTITY_RISK:
                attrs["severity"] = row.severity
            if entity_type == ENTITY_TASK:
                attrs["status"] = row.status
                attrs["owner"] = row.owner
            created = await upsert_entity(
                session,
                entity_id=entity_id,
                entity_type=entity_type,
                canonical_name=str(row.title)[:255],
                attrs=attrs,
            )
            if created:
                counts["nodes_created"] += 1
            for project_id in await _project_links_for_text(
                session, text=str(row.title)
            ):
                if await upsert_link(
                    session,
                    from_entity_id=entity_id,
                    relation=project_relation,
                    to_entity_id=project_id,
                    evidence_refs=list(row.evidence_refs or [])[:3],
                    confidence=0.7,
                ):
                    counts["links_created"] += 1
    return counts


async def run_graph_lift(session: AsyncSession, *, now: Any = None) -> dict[str, int]:
    people = await lift_people(session, now=now)
    extracted = await lift_extracted(session)
    return {
        "people_created": people["people_created"],
        "merge_proposals": people["merge_proposals"],
        "nodes_created": extracted["nodes_created"],
        "links_created": people["links_created"] + extracted["links_created"],
    }
