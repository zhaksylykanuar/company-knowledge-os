"""Knowledge graph ontology and idempotent node/link upserts.

The graph reuses the existing ``entities`` / ``entity_links`` tables.
This module fixes the vocabulary (entity types and relations) for the
second-opinion platform and provides upsert helpers all agents share.
Every link carries ``evidence_refs`` and ``confidence``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord

ENTITY_PROJECT = "project"
ENTITY_JIRA_PROJECT = "jira_project"
ENTITY_REPOSITORY = "repository"
ENTITY_PERSON = "person"
ENTITY_CLIENT = "client"
ENTITY_DEAL = "deal"
ENTITY_MEETING = "meeting"
ENTITY_DECISION = "decision"
ENTITY_RISK = "risk"
ENTITY_TASK = "task"
ENTITY_HYPOTHESIS = "hypothesis"

ENTITY_TYPES = frozenset(
    {
        ENTITY_PROJECT,
        ENTITY_JIRA_PROJECT,
        ENTITY_REPOSITORY,
        ENTITY_PERSON,
        ENTITY_CLIENT,
        ENTITY_DEAL,
        ENTITY_MEETING,
        ENTITY_DECISION,
        ENTITY_RISK,
        ENTITY_TASK,
        ENTITY_HYPOTHESIS,
    }
)

REL_BELONGS_TO = "belongs_to"
REL_WORKS_ON = "works_on"
REL_EMPLOYED_BY = "employed_by"
REL_MENTIONS = "mentions"
REL_DECIDED_IN = "decided_in"
REL_AFFECTS = "affects"
REL_SUPPORTS = "supports"
REL_REFUTES = "refutes"
REL_NEXT_STEP_OF = "next_step_of"

RELATIONS = frozenset(
    {
        REL_BELONGS_TO,
        REL_WORKS_ON,
        REL_EMPLOYED_BY,
        REL_MENTIONS,
        REL_DECIDED_IN,
        REL_AFFECTS,
        REL_SUPPORTS,
        REL_REFUTES,
        REL_NEXT_STEP_OF,
    }
)

_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def slugify(value: str) -> str:
    """Stable slug for entity ids; keeps non-latin scripts (Cyrillic names)."""

    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    slug = _SLUG_RE.sub("-", normalized).replace("_", "-").strip("-")
    return slug or "unknown"


def person_entity_id(display_name: str) -> str:
    return f"person:{slugify(display_name)}"


def link_id(from_entity_id: str, relation: str, to_entity_id: str) -> str:
    return f"{from_entity_id}->{relation}->{to_entity_id}"


async def upsert_entity(
    session: AsyncSession,
    *,
    entity_id: str,
    entity_type: str,
    canonical_name: str,
    attrs: dict[str, Any] | None = None,
) -> bool:
    """Create the entity if missing; merge new attrs into existing ones.

    Returns True when a new entity row was created.
    """

    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type: {entity_type}")

    from app.services.run_context import get_run_id

    run_id = get_run_id()
    existing = await session.scalar(
        select(EntityRecord).where(EntityRecord.entity_id == entity_id)
    )
    if existing is None:
        session.add(
            EntityRecord(
                entity_id=entity_id,
                entity_type=entity_type,
                canonical_name=canonical_name,
                attrs=dict(attrs or {}),
                created_by_run_id=run_id,
                updated_by_run_id=run_id,
            )
        )
        await session.flush()
        return True

    merged = dict(existing.attrs or {})
    changed = False
    for key, value in (attrs or {}).items():
        if merged.get(key) != value:
            merged[key] = value
            changed = True
    if changed:
        existing.attrs = merged
        existing.updated_by_run_id = run_id
        await session.flush()
    return False


async def upsert_link(
    session: AsyncSession,
    *,
    from_entity_id: str,
    relation: str,
    to_entity_id: str,
    evidence_refs: list[dict[str, Any]] | None = None,
    confidence: float = 1.0,
) -> bool:
    """Create the link if missing. Returns True when created."""

    if relation not in RELATIONS:
        raise ValueError(f"unknown relation: {relation}")

    lid = link_id(from_entity_id, relation, to_entity_id)
    existing = await session.scalar(
        select(EntityLinkRecord).where(EntityLinkRecord.link_id == lid)
    )
    if existing is not None:
        return False
    from app.services.run_context import get_run_id

    session.add(
        EntityLinkRecord(
            link_id=lid,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            relation=relation,
            evidence_refs=list(evidence_refs or []),
            confidence=confidence,
            created_by_run_id=get_run_id(),
        )
    )
    await session.flush()
    return True


async def upsert_alias(
    session: AsyncSession,
    *,
    entity_id: str,
    alias: str,
    source: str,
    confidence: float = 1.0,
) -> bool:
    """Register an alias for resolution. Returns True when created."""

    from app.services.entity_resolution import normalize_alias

    normalized = normalize_alias(alias)
    if not normalized:
        return False
    existing = await session.scalar(
        select(EntityAliasRecord)
        .where(EntityAliasRecord.entity_id == entity_id)
        .where(EntityAliasRecord.normalized_alias == normalized)
    )
    if existing is not None:
        return False
    session.add(
        EntityAliasRecord(
            entity_id=entity_id,
            alias=alias,
            normalized_alias=normalized,
            source=source,
            confidence=confidence,
            confirmed_by_user=False,
        )
    )
    await session.flush()
    return True
