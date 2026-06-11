"""Jira project -> knowledge graph mapping (vision Phase A3).

Persists the human-confirmed mapping between Jira project keys and graph
project entities: a ``jira_project`` entity per key plus a ``belongs_to``
link to the target project. Idempotent; graph rows only.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.services.entity_resolution import normalize_alias

ENTITY_TYPE_JIRA_PROJECT = "jira_project"
RELATION_BELONGS_TO = "belongs_to"


def jira_entity_id(jira_key: str) -> str:
    return f"jira:{jira_key.upper()}"


async def persist_jira_project_mapping(
    session: AsyncSession,
    mapping: dict[str, str],
) -> dict[str, int]:
    """Upsert jira_project entities, aliases and belongs_to links."""

    entities_created = 0
    links_created = 0
    for raw_key, target_entity_id in mapping.items():
        key = raw_key.strip().upper()
        if not key:
            continue
        target = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == target_entity_id)
        )
        if target is None:
            raise ValueError(f"target entity not found: {target_entity_id}")

        source_id = jira_entity_id(key)
        existing = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == source_id)
        )
        if existing is None:
            session.add(
                EntityRecord(
                    entity_id=source_id,
                    entity_type=ENTITY_TYPE_JIRA_PROJECT,
                    canonical_name=key,
                    attrs={"jira_key": key},
                )
            )
            entities_created += 1

        normalized = normalize_alias(key)
        existing_alias = await session.scalar(
            select(EntityAliasRecord)
            .where(EntityAliasRecord.entity_id == source_id)
            .where(EntityAliasRecord.normalized_alias == normalized)
        )
        if existing_alias is None and normalized:
            session.add(
                EntityAliasRecord(
                    entity_id=source_id,
                    alias=key,
                    normalized_alias=normalized,
                    source="jira_mapping",
                    confidence=1.0,
                    confirmed_by_user=True,
                )
            )

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
                    evidence_refs=[
                        {"kind": "jira_project_search", "jira_key": key}
                    ],
                    confidence=1.0,
                )
            )
            links_created += 1

    await session.flush()
    return {"entities_created": entities_created, "links_created": links_created}


async def jira_keys_for_project(
    session: AsyncSession,
    project_entity_id: str,
) -> list[str]:
    """Jira project keys mapped to a graph project (via belongs_to links)."""

    rows = (
        await session.execute(
            select(EntityRecord.attrs)
            .join(
                EntityLinkRecord,
                EntityLinkRecord.from_entity_id == EntityRecord.entity_id,
            )
            .where(EntityLinkRecord.to_entity_id == project_entity_id)
            .where(EntityLinkRecord.relation == RELATION_BELONGS_TO)
            .where(EntityRecord.entity_type == ENTITY_TYPE_JIRA_PROJECT)
        )
    ).all()
    keys = sorted(
        {
            str(attrs.get("jira_key"))
            for (attrs,) in rows
            if isinstance(attrs, dict) and attrs.get("jira_key")
        }
    )
    return keys


async def jira_issue_count_for_keys(
    session: AsyncSession,
    keys: list[str],
) -> int:
    """Distinct synced Jira issues for the given project keys."""

    if not keys:
        return 0
    from sqlalchemy import func, or_

    from app.db.event_models import SourceEvent

    count = await session.scalar(
        select(func.count(func.distinct(SourceEvent.source_object_id)))
        .where(SourceEvent.source_system == "jira")
        .where(
            or_(*[SourceEvent.source_object_id.like(f"{key}-%") for key in keys])
        )
    )
    return int(count or 0)


async def all_mapped_jira_keys(session: AsyncSession) -> dict[str, str]:
    """All mapped jira keys -> target project entity id."""

    rows = (
        await session.execute(
            select(EntityRecord.attrs, EntityLinkRecord.to_entity_id)
            .join(
                EntityLinkRecord,
                EntityLinkRecord.from_entity_id == EntityRecord.entity_id,
            )
            .where(EntityLinkRecord.relation == RELATION_BELONGS_TO)
            .where(EntityRecord.entity_type == ENTITY_TYPE_JIRA_PROJECT)
        )
    ).all()
    return {
        str(attrs["jira_key"]): str(target)
        for attrs, target in rows
        if isinstance(attrs, dict) and attrs.get("jira_key")
    }
