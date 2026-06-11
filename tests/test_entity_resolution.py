from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal, engine
from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.services.entity_resolution import (
    ENTITY_TYPE_PROJECT,
    SEED_PROJECT_ALIASES,
    normalize_alias,
    resolve_entities_in_text,
    seed_project_entities,
)
from app.services.telegram_founder_bot import build_status_reply_text


async def _ensure_graph_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(EntityRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityAliasRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityLinkRecord.__table__.create, checkfirst=True)


async def _cleanup_seed() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(EntityAliasRecord).where(
                EntityAliasRecord.entity_id.in_(list(SEED_PROJECT_ALIASES))
            )
        )
        await session.execute(
            delete(EntityRecord).where(
                EntityRecord.entity_id.in_(list(SEED_PROJECT_ALIASES))
            )
        )
        await session.commit()


def test_normalize_alias_variants() -> None:
    assert normalize_alias("S-SAP") == "ssap"
    assert normalize_alias("ССАП") == "ссап"
    assert normalize_alias("q Twin") == "qtwin"
    assert normalize_alias("Integra City Solutions") == "integracitysolutions"
    assert normalize_alias("Ёлка") == "елка"
    assert normalize_alias("!!!") == ""


async def test_seed_is_idempotent_and_resolution_matches_variants() -> None:
    await _ensure_graph_tables()
    await _cleanup_seed()
    try:
        async with AsyncSessionLocal() as session:
            first = await seed_project_entities(session)
            await session.commit()
        async with AsyncSessionLocal() as session:
            second = await seed_project_entities(session)
            await session.commit()

        assert first["entities_created"] == 3
        assert first["aliases_created"] > 0
        assert second == {"entities_created": 0, "aliases_created": 0}

        async with AsyncSessionLocal() as session:
            for question, expected_entity in (
                ("что у нас с SSAP?", "project:ssap"),
                ("Что по S-SAP сегодня", "project:ssap"),
                ("что у нас с ссап", "project:ssap"),
                ("статус q twin", "project:qtwin"),
                ("что по qaztwin", "project:qtwin"),
                ("Что у нас по Интегра Сити Солюшнс?", "project:integra"),
                ("integra city status", "project:integra"),
            ):
                resolved = await resolve_entities_in_text(
                    session,
                    question,
                    entity_type=ENTITY_TYPE_PROJECT,
                )
                assert resolved, question
                assert resolved[0].entity_id == expected_entity, question

            none_resolved = await resolve_entities_in_text(
                session,
                "просто привет без проектов",
                entity_type=ENTITY_TYPE_PROJECT,
            )
            assert none_resolved == []
    finally:
        await _cleanup_seed()


async def test_status_reply_names_recognized_project() -> None:
    await _ensure_graph_tables()
    await _cleanup_seed()
    try:
        async with AsyncSessionLocal() as session:
            await seed_project_entities(session)
            await session.commit()

        text = await build_status_reply_text(
            window_hours=1,
            now=datetime(2199, 7, 1, tzinfo=timezone.utc),
            question_text="что у нас с SSAP?",
        )

        assert "📂 Проект: SSAP" in text
        assert "🧠 Дайджест внимания" in text
    finally:
        await _cleanup_seed()


async def test_status_reply_without_project_has_no_prefix() -> None:
    await _ensure_graph_tables()
    text = await build_status_reply_text(
        window_hours=1,
        now=datetime(2199, 7, 1, tzinfo=timezone.utc),
        question_text="/status",
    )

    assert "📂 Проект:" not in text
    assert text.startswith("🧠 Дайджест внимания")
