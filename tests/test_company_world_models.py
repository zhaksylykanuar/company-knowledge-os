"""Schema contract tests for the durable Company World foundation."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, delete, select, text
from sqlalchemy.exc import IntegrityError

from migrations.versions import (
    a3c4d5e6f7b8_add_company_world_foundation as company_world_migration,
)

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import SourceRecord
from app.db.company_world_models import (
    AFFILIATION_RELATIONSHIP_CONTACT,
    INTERACTION_DIRECTION_INBOUND,
    ORGANIZATION_RELATIONSHIP_PROSPECT,
    PERSON_ORIGIN_FOUNDER_CONFIRMATION,
    RESOLUTION_CANDIDATE_EXTERNAL_PERSON,
    RESOLUTION_DECISION_CONFIRMED,
    Affiliation,
    CompanyWorldResolution,
    Interaction,
    Organization,
    Person,
)
from app.db.identity_models import MEMBERSHIP_ROLE_OWNER, Membership, User, Workspace


async def _create_workspace(marker: str, suffix: str) -> tuple[User, Workspace]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"company-world-{marker}-{suffix}@example.test",
            name=f"Owner {suffix}",
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Company World {suffix}",
            slug=f"company-world-{marker}-{suffix}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )
        )
        await session.commit()
        return user, workspace


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"company-world-{marker}-%"))
                )
            ).scalars()
        )
        if workspace_ids:
            for model in (
                CompanyWorldResolution,
                Interaction,
                Affiliation,
                Organization,
                Person,
                SourceRecord,
                Membership,
            ):
                await session.execute(delete(model).where(model.workspace_id.in_(workspace_ids)))
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        await session.execute(delete(User).where(User.email.like(f"company-world-{marker}-%")))
        await session.commit()


def test_company_world_models_register_without_raw_message_content() -> None:
    assert {
        Person.__tablename__,
        Organization.__tablename__,
        Affiliation.__tablename__,
        Interaction.__tablename__,
        CompanyWorldResolution.__tablename__,
    } == {
        "people",
        "organizations",
        "affiliations",
        "interactions",
        "company_world_resolutions",
    }
    assert "body" not in Interaction.__table__.c
    assert "snippet" not in Interaction.__table__.c
    assert "ck_people_membership_user" in {
        constraint.name for constraint in Person.__table__.constraints
    }


def test_people_membership_user_check_is_synced_between_orm_and_migration(
    monkeypatch,
) -> None:
    created_tables: dict[str, tuple[object, ...]] = {}

    def _capture_table(
        table_name: str,
        *elements: object,
        **_kwargs: object,
    ) -> None:
        created_tables[table_name] = elements

    monkeypatch.setattr(company_world_migration.op, "create_table", _capture_table)
    monkeypatch.setattr(
        company_world_migration.op,
        "create_unique_constraint",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        company_world_migration.op,
        "create_index",
        lambda *_args, **_kwargs: None,
    )

    company_world_migration.upgrade()

    migration_check = next(
        element
        for element in created_tables["people"]
        if isinstance(element, CheckConstraint) and element.name == "ck_people_membership_user"
    )
    orm_check = next(
        constraint
        for constraint in Person.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_people_membership_user"
    )
    assert str(migration_check.sqltext) == str(orm_check.sqltext)


async def test_company_world_profile_roundtrip() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        owner, workspace = await _create_workspace(marker, "one")
        occurred_at = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            source = SourceRecord(
                workspace_id=workspace.id,
                provider="gmail",
                external_id=f"message-{marker}",
                record_type="message",
                payload={},
                payload_hash=f"hash-{marker}",
                observed_at=occurred_at,
            )
            person = Person(
                workspace_id=workspace.id,
                normalized_email=f"contact-{marker}@customer.test",
                display_name="Customer Contact",
                origin=PERSON_ORIGIN_FOUNDER_CONFIRMATION,
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            organization = Organization(
                workspace_id=workspace.id,
                canonical_key=f"domain:customer-{marker}.test",
                normalized_domain=f"customer-{marker}.test",
                display_name="Customer",
                relationship_kind=ORGANIZATION_RELATIONSHIP_PROSPECT,
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            session.add_all([source, person, organization])
            await session.flush()
            affiliation = Affiliation(
                workspace_id=workspace.id,
                person_id=person.id,
                organization_id=organization.id,
                relationship_type=AFFILIATION_RELATIONSHIP_CONTACT,
                source_record_id=source.id,
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            session.add(affiliation)
            await session.flush()
            interaction = Interaction(
                workspace_id=workspace.id,
                person_id=person.id,
                organization_id=organization.id,
                source_record_id=source.id,
                direction=INTERACTION_DIRECTION_INBOUND,
                subject="Hello",
                occurred_at=occurred_at,
            )
            resolution = CompanyWorldResolution(
                workspace_id=workspace.id,
                candidate_type=RESOLUTION_CANDIDATE_EXTERNAL_PERSON,
                candidate_key=f"external-person:{marker}",
                candidate_version="b" * 64,
                decision=RESOLUTION_DECISION_CONFIRMED,
                idempotency_key=f"confirm-{marker}",
                request_hash="a" * 64,
                actor_user_id=owner.id,
                source_record_id=source.id,
                result_person_id=person.id,
                result_organization_id=organization.id,
                result_affiliation_id=affiliation.id,
            )
            session.add_all([interaction, resolution])
            await session.commit()

            stored = await session.scalar(
                select(CompanyWorldResolution).where(CompanyWorldResolution.id == resolution.id)
            )
            assert stored is not None
            assert stored.result_person_id == person.id
            assert stored.result_affiliation_id == affiliation.id
    finally:
        await _cleanup(marker)


async def test_composite_fks_reject_cross_workspace_affiliation() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        owner_one, workspace_one = await _create_workspace(marker, "one")
        owner_two, workspace_two = await _create_workspace(marker, "two")
        occurred_at = datetime(2026, 7, 13, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            person = Person(
                workspace_id=workspace_one.id,
                normalized_email=f"person-{marker}@example.test",
                display_name="Person One",
                origin=PERSON_ORIGIN_FOUNDER_CONFIRMATION,
                confirmed_by_user_id=owner_one.id,
                confirmed_at=occurred_at,
            )
            organization = Organization(
                workspace_id=workspace_two.id,
                canonical_key=f"domain:cross-{marker}.test",
                display_name="Organization Two",
                confirmed_by_user_id=owner_two.id,
                confirmed_at=occurred_at,
            )
            source = SourceRecord(
                workspace_id=workspace_one.id,
                provider="gmail",
                external_id=f"cross-{marker}",
                record_type="message",
                payload={},
                payload_hash=f"cross-{marker}",
                observed_at=occurred_at,
            )
            session.add_all([person, organization, source])
            await session.flush()
            session.add(
                Affiliation(
                    workspace_id=workspace_one.id,
                    person_id=person.id,
                    organization_id=organization.id,
                    relationship_type=AFFILIATION_RELATIONSHIP_CONTACT,
                    source_record_id=source.id,
                    confirmed_by_user_id=owner_one.id,
                    confirmed_at=occurred_at,
                )
            )
            with pytest.raises(
                IntegrityError,
                match="fk_affiliations_workspace_organization",
            ):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_membership_bound_fk_rejects_cross_workspace_person_user() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        _owner_one, workspace_one = await _create_workspace(marker, "one")
        owner_two, _workspace_two = await _create_workspace(marker, "two")
        async with AsyncSessionLocal() as session:
            session.add(
                Person(
                    workspace_id=workspace_one.id,
                    user_id=owner_two.id,
                    normalized_email=owner_two.email,
                    display_name=owner_two.name,
                    origin="membership",
                )
            )
            with pytest.raises(IntegrityError, match="fk_people_workspace_user"):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_resolution_affiliation_identity_must_match_results() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        owner, workspace = await _create_workspace(marker, "one")
        occurred_at = datetime(2026, 7, 13, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            source = SourceRecord(
                workspace_id=workspace.id,
                provider="gmail",
                external_id=f"identity-{marker}",
                record_type="message",
                payload={},
                payload_hash=f"identity-{marker}",
                observed_at=occurred_at,
            )
            person_one = Person(
                workspace_id=workspace.id,
                normalized_email=f"one-{marker}@example.test",
                origin=PERSON_ORIGIN_FOUNDER_CONFIRMATION,
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            person_two = Person(
                workspace_id=workspace.id,
                normalized_email=f"two-{marker}@example.test",
                origin=PERSON_ORIGIN_FOUNDER_CONFIRMATION,
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            organization = Organization(
                workspace_id=workspace.id,
                canonical_key=f"domain:identity-{marker}.test",
                display_name="Identity Organization",
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            session.add_all([source, person_one, person_two, organization])
            await session.flush()
            affiliation = Affiliation(
                workspace_id=workspace.id,
                person_id=person_one.id,
                organization_id=organization.id,
                relationship_type=AFFILIATION_RELATIONSHIP_CONTACT,
                source_record_id=source.id,
                confirmed_by_user_id=owner.id,
                confirmed_at=occurred_at,
            )
            session.add(affiliation)
            await session.flush()
            session.add(
                CompanyWorldResolution(
                    workspace_id=workspace.id,
                    candidate_type=RESOLUTION_CANDIDATE_EXTERNAL_PERSON,
                    candidate_key=f"external-person:mismatch-{marker}",
                    candidate_version="b" * 64,
                    decision=RESOLUTION_DECISION_CONFIRMED,
                    idempotency_key=f"mismatch-{marker}",
                    request_hash="a" * 64,
                    actor_user_id=owner.id,
                    source_record_id=source.id,
                    result_person_id=person_two.id,
                    result_organization_id=organization.id,
                    result_affiliation_id=affiliation.id,
                )
            )
            with pytest.raises(
                IntegrityError,
                match="fk_company_world_resolutions_result_affiliation_identity",
            ):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


def test_company_world_downgrade_refuses_non_empty_tables(monkeypatch) -> None:
    class _Result:
        @staticmethod
        def scalar_one() -> bool:
            return True

    class _Bind:
        @staticmethod
        def execute(_statement: object) -> _Result:
            return _Result()

    monkeypatch.setattr(company_world_migration.op, "get_bind", lambda: _Bind())
    with pytest.raises(RuntimeError, match="refusing to downgrade non-empty"):
        company_world_migration.downgrade()


def test_company_world_downgrade_locks_all_tables_before_empty_checks(
    monkeypatch,
) -> None:
    statements: list[str] = []
    dropped_tables: list[str] = []

    class _Result:
        @staticmethod
        def scalar_one() -> bool:
            return False

    class _Bind:
        @staticmethod
        def execute(statement: object) -> _Result:
            statements.append(str(statement))
            return _Result()

    monkeypatch.setattr(company_world_migration.op, "get_bind", lambda: _Bind())
    monkeypatch.setattr(
        company_world_migration.op,
        "drop_table",
        dropped_tables.append,
    )
    monkeypatch.setattr(
        company_world_migration.op,
        "drop_constraint",
        lambda *_args, **_kwargs: None,
    )

    company_world_migration.downgrade()

    expected_locks = [
        f'LOCK TABLE "{table_name}" IN ACCESS EXCLUSIVE MODE'
        for table_name in company_world_migration.COMPANY_WORLD_LOCK_ORDER
    ]
    lock_count = len(expected_locks)
    assert statements[:lock_count] == expected_locks
    assert all(statement.startswith("SELECT EXISTS") for statement in statements[lock_count:])
    assert dropped_tables == list(company_world_migration.COMPANY_WORLD_TABLES)


async def test_company_world_migration_contract_exists() -> None:
    async with AsyncSessionLocal() as session:
        tables = set(
            (
                await session.execute(
                    text(
                        """
                        select table_name from information_schema.tables
                        where table_schema = 'public'
                        and table_name in (
                          'people', 'organizations', 'affiliations',
                          'interactions', 'company_world_resolutions'
                        )
                        """
                    )
                )
            ).scalars()
        )
        constraints = set(
            (
                await session.execute(
                    text(
                        """
                        select conname from pg_constraint
                        where conname in (
                          'uq_source_records_workspace_id_id',
                          'uq_people_workspace_id_id',
                          'uq_organizations_workspace_id_id',
                          'uq_affiliations_workspace_id_id',
                          'uq_interactions_workspace_id_id',
                          'uq_company_world_resolutions_workspace_id_id',
                          'ck_people_confirmation_provenance',
                          'fk_people_workspace_user',
                          'fk_people_workspace_confirmed_by',
                          'fk_organizations_workspace_confirmed_by',
                          'fk_affiliations_workspace_person',
                          'fk_affiliations_workspace_organization',
                          'fk_affiliations_workspace_confirmed_by',
                          'uq_affiliations_workspace_identity',
                          'fk_interactions_workspace_source_record',
                          'fk_company_world_resolutions_workspace_actor',
                          'fk_company_world_resolutions_result_affiliation_identity',
                          'uq_company_world_resolutions_workspace_idempotency_key',
                          'uq_company_world_resolutions_workspace_candidate'
                        )
                        """
                    )
                )
            ).scalars()
        )

    assert tables == {
        "people",
        "organizations",
        "affiliations",
        "interactions",
        "company_world_resolutions",
    }
    assert constraints == {
        "uq_source_records_workspace_id_id",
        "uq_people_workspace_id_id",
        "uq_organizations_workspace_id_id",
        "uq_affiliations_workspace_id_id",
        "uq_interactions_workspace_id_id",
        "uq_company_world_resolutions_workspace_id_id",
        "ck_people_confirmation_provenance",
        "fk_people_workspace_user",
        "fk_people_workspace_confirmed_by",
        "fk_organizations_workspace_confirmed_by",
        "fk_affiliations_workspace_person",
        "fk_affiliations_workspace_organization",
        "fk_affiliations_workspace_confirmed_by",
        "uq_affiliations_workspace_identity",
        "fk_interactions_workspace_source_record",
        "fk_company_world_resolutions_workspace_actor",
        "fk_company_world_resolutions_result_affiliation_identity",
        "uq_company_world_resolutions_workspace_idempotency_key",
        "uq_company_world_resolutions_workspace_candidate",
    }
