from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal, engine
from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.db.status_models import StatusSnapshotRecord
from app.services.entity_resolution import (
    ENTITY_TYPE_PROJECT,
    SEED_PROJECT_ALIASES,
    normalize_alias,
    resolve_entities_in_text,
    seed_project_entities,
)
from app.services import telegram_founder_bot as bot
from app.services.telegram_founder_bot import build_status_reply_text

# Уникальные нормализованные алиасы из seed-словаря (дубликаты схлопываются).
EXPECTED_SEED_ALIAS_COUNT = sum(
    len({normalize_alias(a) for a in aliases if normalize_alias(a)})
    for _name, aliases in SEED_PROJECT_ALIASES.values()
)


async def _ensure_graph_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(EntityRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityAliasRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityLinkRecord.__table__.create, checkfirst=True)
        await conn.run_sync(StatusSnapshotRecord.__table__.create, checkfirst=True)


async def _seed() -> None:
    """Idempotent seed; intentionally NOT cleaned up.

    Tests share the local dev database with the operator seed command, so
    deleting seed rows here would silently break the live founder bot.
    """

    await _ensure_graph_tables()
    async with AsyncSessionLocal() as session:
        await seed_project_entities(session)
        await session.commit()


def test_normalize_alias_variants() -> None:
    assert normalize_alias("S-SAP") == "ssap"
    assert normalize_alias("ССАП") == "ссап"
    assert normalize_alias("q Twin") == "qtwin"
    assert normalize_alias("Integra City Solutions") == "integracitysolutions"
    assert normalize_alias("Ёлка") == "елка"
    assert normalize_alias("!!!") == ""


async def test_seed_is_idempotent_and_complete() -> None:
    await _seed()

    async with AsyncSessionLocal() as session:
        second = await seed_project_entities(session)
        await session.commit()

        seed_ids = list(SEED_PROJECT_ALIASES)
        entities = await session.scalar(
            select(func.count())
            .select_from(EntityRecord)
            .where(EntityRecord.entity_id.in_(seed_ids))
        )
        aliases = await session.scalar(
            select(func.count())
            .select_from(EntityAliasRecord)
            .where(EntityAliasRecord.entity_id.in_(seed_ids))
        )

    assert second == {"entities_created": 0, "aliases_created": 0}
    assert entities == len(SEED_PROJECT_ALIASES)
    assert aliases == EXPECTED_SEED_ALIAS_COUNT


async def test_resolution_matches_ru_en_variants() -> None:
    await _seed()

    async with AsyncSessionLocal() as session:
        for question, expected_entity in (
            ("что у нас с SSAP?", "project:ssap"),
            ("Что по S-SAP сегодня", "project:ssap"),
            ("что с ссап", "project:ssap"),
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


async def test_status_reply_names_recognized_project() -> None:
    await _seed()

    text = await build_status_reply_text(
        window_hours=1,
        now=datetime(2199, 7, 1, tzinfo=timezone.utc),
        question_text="что у нас с SSAP?",
    )

    assert text is not None
    # Two legitimate branches depending on whether the shared local dev DB
    # has Jira projects mapped to SSAP: a project snapshot, or the digest
    # fallback with an explicit project prefix.
    if "Snapshot: SSAP" in text:
        # A Jira-status snapshot of the recognized project. When Jira keys are
        # mapped it shows "статус по Jira (<keys>)"; on a fresh database with
        # no mapped issues it honestly reports "no Jira keys". Both name the
        # recognized project.
        assert ("статус по Jira" in text) or ("no Jira keys" in text)
    else:
        assert "📂 Проект: SSAP" in text
        assert "🧠 Дайджест внимания" in text


async def test_free_text_with_alias_only_returns_project_status() -> None:
    from app.services.telegram_founder_bot import build_reply_for_update

    await _seed()

    update = {
        "update_id": 1,
        "message": {"chat": {"id": "777"}, "text": "ssap когда релиз?"},
    }
    reply = await build_reply_for_update(
        update,
        allowed_chat_id="777",
        window_hours=1,
        now=datetime(2199, 7, 2, tzinfo=timezone.utc),
    )

    assert reply is not None
    # Same two-branch contract as test_status_reply_names_recognized_project.
    assert "Snapshot: SSAP" in reply or "📂 Проект: SSAP" in reply


async def test_status_reply_without_project_has_no_prefix(
    monkeypatch,
) -> None:
    organization_id = f"test-org-{uuid4().hex}"
    snapshot = type(
        "Snapshot",
        (),
        {
            "status_color": "unknown",
            "confidence": 0.20,
            "what_changed": ({"field": "snapshot", "change": "created"},),
            "summary": "Project Alpha: unknown; Jira no Jira keys; 0 issues.",
            "evidence_source_ids": (),
        },
    )()

    async def fake_project_snapshots(*_args, **_kwargs):
        return [(bot._ProjectEntity("project:alpha", "Project Alpha"), snapshot)]

    monkeypatch.setattr(bot, "_build_all_project_snapshots", fake_project_snapshots)

    text: str | None = None
    try:
        text = await build_status_reply_text(
            window_hours=1,
            now=datetime(2199, 7, 1, tzinfo=timezone.utc),
            question_text="/status",
            organization_id=organization_id,
        )
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(StatusSnapshotRecord).where(
                    StatusSnapshotRecord.organization_id == organization_id
                )
            )
            await session.commit()

    assert text is not None
    assert "📂 Проект:" not in text
    assert text.startswith("📊 Project snapshots")
    assert "No project snapshots with evidence yet." in text
    assert "⚪" not in text
    assert "unknown; Jira no Jira keys; 0 issues" not in text
