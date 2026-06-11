"""GitHub repository -> knowledge graph mapping (vision Phase A4).

Mirrors the Jira mapping: a ``repository`` entity per repo plus a
``belongs_to`` link to the target project. Idempotent; graph rows only.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.services.jira_graph_mapping import RELATION_BELONGS_TO

ENTITY_TYPE_REPOSITORY = "repository"


def repo_entity_id(org: str, repo: str) -> str:
    return f"repo:{org}/{repo}"


async def persist_github_repo_mapping(
    session: AsyncSession,
    *,
    org: str,
    mapping: dict[str, str],
) -> dict[str, int]:
    """Upsert repository entities and belongs_to links."""

    entities_created = 0
    links_created = 0
    for raw_repo, target_entity_id in mapping.items():
        repo = raw_repo.strip()
        if not repo:
            continue
        target = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == target_entity_id)
        )
        if target is None:
            raise ValueError(f"target entity not found: {target_entity_id}")

        source_id = repo_entity_id(org, repo)
        existing = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == source_id)
        )
        if existing is None:
            session.add(
                EntityRecord(
                    entity_id=source_id,
                    entity_type=ENTITY_TYPE_REPOSITORY,
                    canonical_name=f"{org}/{repo}",
                    attrs={"org": org, "repo": repo},
                )
            )
            entities_created += 1

        link_id = f"{source_id}->{RELATION_BELONGS_TO}->{target_entity_id}"
        existing_link = await session.scalar(
            select(EntityLinkRecord).where(EntityLinkRecord.link_id == link_id)
        )
        if existing_link is None:
            session.add(
                EntityLinkRecord(
                    link_id=link_id,
                    from_entity_id=source_id,
                    to_entity_id=target_entity_id,
                    relation=RELATION_BELONGS_TO,
                    evidence_refs=[{"kind": "github_org_repos", "org": org, "repo": repo}],
                    confidence=1.0,
                )
            )
            links_created += 1

    await session.flush()
    return {"entities_created": entities_created, "links_created": links_created}


async def repos_for_project(
    session: AsyncSession,
    project_entity_id: str,
) -> list[dict[str, str]]:
    """[{org, repo}] mapped to a graph project via belongs_to links."""

    rows = (
        await session.execute(
            select(EntityRecord.attrs)
            .join(
                EntityLinkRecord,
                EntityLinkRecord.from_entity_id == EntityRecord.entity_id,
            )
            .where(EntityLinkRecord.to_entity_id == project_entity_id)
            .where(EntityLinkRecord.relation == RELATION_BELONGS_TO)
            .where(EntityRecord.entity_type == ENTITY_TYPE_REPOSITORY)
        )
    ).all()
    repos = [
        {"org": str(attrs["org"]), "repo": str(attrs["repo"])}
        for (attrs,) in rows
        if isinstance(attrs, dict) and attrs.get("org") and attrs.get("repo")
    ]
    return sorted(repos, key=lambda item: (item["org"], item["repo"]))


async def all_mapped_repos(session: AsyncSession) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(EntityRecord.attrs, EntityLinkRecord.to_entity_id)
            .join(
                EntityLinkRecord,
                EntityLinkRecord.from_entity_id == EntityRecord.entity_id,
            )
            .where(EntityLinkRecord.relation == RELATION_BELONGS_TO)
            .where(EntityRecord.entity_type == ENTITY_TYPE_REPOSITORY)
        )
    ).all()
    return sorted(
        (
            {
                "org": str(attrs["org"]),
                "repo": str(attrs["repo"]),
                "project_entity_id": str(target),
            }
            for attrs, target in rows
            if isinstance(attrs, dict) and attrs.get("org") and attrs.get("repo")
        ),
        key=lambda item: (item["org"], item["repo"]),
    )
