"""Entity resolution: aliases -> canonical entities (vision Phase A2).

Deterministic, read-oriented resolution: normalize text, match known aliases,
return entities with confidence. Seeding canonical project aliases is a
separate explicit local write command. No LLM calls; LLM-assisted alias
suggestions arrive in a later slice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.graph_models import EntityAliasRecord, EntityRecord

ENTITY_TYPE_PROJECT = "project"

# Canonical seed: the three pilot projects from the vision document.
SEED_PROJECT_ALIASES: dict[str, tuple[str, tuple[str, ...]]] = {
    "project:ssap": (
        "SSAP",
        ("SSAP", "S-SAP", "ССАП", "ссап", "s sap"),
    ),
    "project:qtwin": (
        "qTwin",
        ("qTwin", "qtw", "q twin", "кьютвин", "qaztwin", "qtwin-io"),
    ),
    "project:integra": (
        "Интегра Сити Солюшнс",
        (
            "Интегра",
            "Интегра Сити",
            "Интегра Сити Солюшнс",
            "Integra",
            "Integra City",
            "Integra City Solutions",
        ),
    ),
}

_NORMALIZE_RE = re.compile(r"[^0-9a-zа-я]+")


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    entity_type: str
    canonical_name: str
    matched_alias: str
    confidence: float


def normalize_alias(value: str) -> str:
    """Casefold, ё->е, strip everything except letters/digits."""

    lowered = value.casefold().replace("ё", "е")
    return _NORMALIZE_RE.sub("", lowered)


async def resolve_entities_in_text(
    session: AsyncSession,
    text: str,
    *,
    entity_type: str | None = None,
) -> list[ResolvedEntity]:
    """Match known aliases inside free text; longest alias wins per entity."""

    normalized_text = normalize_alias(text)
    if not normalized_text:
        return []

    stmt = select(EntityAliasRecord, EntityRecord).join(
        EntityRecord, EntityRecord.entity_id == EntityAliasRecord.entity_id
    )
    if entity_type is not None:
        stmt = stmt.where(EntityRecord.entity_type == entity_type)
    rows = (await session.execute(stmt)).all()

    best: dict[str, ResolvedEntity] = {}
    for alias_row, entity_row in rows:
        normalized = alias_row.normalized_alias
        if not normalized or normalized not in normalized_text:
            continue
        candidate = ResolvedEntity(
            entity_id=entity_row.entity_id,
            entity_type=entity_row.entity_type,
            canonical_name=entity_row.canonical_name,
            matched_alias=alias_row.alias,
            confidence=float(alias_row.confidence),
        )
        current = best.get(entity_row.entity_id)
        if current is None or len(normalized) > len(
            normalize_alias(current.matched_alias)
        ):
            best[entity_row.entity_id] = candidate

    return sorted(
        best.values(),
        key=lambda item: (-len(normalize_alias(item.matched_alias)), item.entity_id),
    )


async def seed_project_entities(session: AsyncSession) -> dict[str, int]:
    """Idempotently upsert the seed projects and their aliases."""

    entities_created = 0
    aliases_created = 0
    for entity_id, (canonical_name, aliases) in SEED_PROJECT_ALIASES.items():
        existing = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == entity_id)
        )
        if existing is None:
            session.add(
                EntityRecord(
                    entity_id=entity_id,
                    entity_type=ENTITY_TYPE_PROJECT,
                    canonical_name=canonical_name,
                    attrs={"seed": True},
                )
            )
            entities_created += 1

        for alias in aliases:
            normalized = normalize_alias(alias)
            if not normalized:
                continue
            existing_alias = await session.scalar(
                select(EntityAliasRecord)
                .where(EntityAliasRecord.entity_id == entity_id)
                .where(EntityAliasRecord.normalized_alias == normalized)
            )
            if existing_alias is not None:
                continue
            session.add(
                EntityAliasRecord(
                    entity_id=entity_id,
                    alias=alias,
                    normalized_alias=normalized,
                    source="seed",
                    confidence=1.0,
                    confirmed_by_user=True,
                )
            )
            aliases_created += 1

    await session.flush()
    return {
        "entities_created": entities_created,
        "aliases_created": aliases_created,
    }
