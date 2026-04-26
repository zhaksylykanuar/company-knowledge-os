from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_scoring import build_score_values


ENTITY_CONFIGS: tuple[tuple[str, type[Any], str], ...] = (
    ("task", ExtractedTask, "tasks_scored"),
    ("risk", ExtractedRisk, "risks_scored"),
    ("decision", ExtractedDecision, "decisions_scored"),
)


async def process_knowledge_scores(
    source_document_id: str | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await process_knowledge_scores_for_session(
            session,
            source_document_id=source_document_id,
        )
        await session.commit()
        return result


async def process_knowledge_scores_for_session(
    session: AsyncSession,
    *,
    source_document_id: str | None = None,
) -> dict[str, Any]:
    created = 0
    updated = 0
    counts = {
        "tasks_scored": 0,
        "risks_scored": 0,
        "decisions_scored": 0,
    }

    for entity_type, model, count_key in ENTITY_CONFIGS:
        statement = select(model)
        if source_document_id:
            statement = statement.where(model.source_document_id == source_document_id)

        result = await session.execute(statement)
        entities = list(result.scalars().all())

        for entity in entities:
            values = build_score_values(
                entity_type=entity_type,
                entity=entity,
            )
            was_created = await _upsert_knowledge_score(session, values)

            if was_created:
                created += 1
            else:
                updated += 1

            counts[count_key] += 1

    return {
        "source_document_id": source_document_id,
        "scores_created": created,
        "scores_updated": updated,
        **counts,
    }


async def _upsert_knowledge_score(
    session: AsyncSession,
    values: dict[str, Any],
) -> bool:
    result = await session.execute(
        select(KnowledgeScore).where(
            KnowledgeScore.entity_type == values["entity_type"],
            KnowledgeScore.entity_id == values["entity_id"],
        )
    )
    existing_score = result.scalar_one_or_none()

    if existing_score is None:
        session.add(KnowledgeScore(**values))
        return True

    for key, value in values.items():
        setattr(existing_score, key, value)

    return False
