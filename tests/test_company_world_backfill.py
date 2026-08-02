from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.company_world_models import Affiliation, Interaction, Organization, Person
from app.services.company_world_backfill_service import backfill_company_world
from tests.test_company_world_resolutions_api import (
    _add_member,
    _bootstrap_workspace,
    _cleanup,
    _company_map,
    _owner_email,
    _organization_candidate,
    _person_candidate,
    _resolve,
    _seed_message,
    _set_auth,
)


async def _confirmed_external_without_interaction(
    *, workspace_id: UUID, marker: str, member_token: str
) -> None:
    await _seed_message(
        workspace_id=workspace_id,
        marker=marker,
        external_id="confirmed-external",
        sender="Confirmed Contact <confirmed@customer.test>",
        recipient=_owner_email(marker),
        occurred_at=datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc),
        raw_body="PRIVATE_BACKFILL_BODY_MUST_NOT_APPEAR",
    )
    company_map = await _company_map(workspace_id=workspace_id, token=member_token)
    candidate = _person_candidate(company_map, "confirmed@customer.test")
    organization_candidate = _organization_candidate(company_map, "customer.test")
    organization_response = await _resolve(
        workspace_id=workspace_id,
        token=member_token,
        payload={
            "candidate_type": "organization",
            "candidate_key": organization_candidate["key"],
            "candidate_version": organization_candidate["candidate_version"],
            "decision": "confirmed",
            "idempotency_key": str(uuid4()),
            "organization_name": "Customer",
            "organization_relationship_kind": "customer",
        },
    )
    assert organization_response.status_code in {200, 201}, organization_response.text
    response = await _resolve(
        workspace_id=workspace_id,
        token=member_token,
        payload={
            "candidate_type": "external_person",
            "candidate_key": candidate["key"],
            "candidate_version": candidate["candidate_version"],
            "decision": "confirmed",
            "idempotency_key": str(uuid4()),
            "display_name": "Confirmed Contact",
            "relationship_type": "employee",
        },
    )
    assert response.status_code in {200, 201}, response.text

    # Simulate a pre-backfill confirmed profile whose source-backed interaction
    # has not been materialized yet.
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Interaction).where(Interaction.workspace_id == workspace_id))
        await session.commit()


async def _seed_backfill_scenario(*, workspace_id: UUID, marker: str, member_token: str) -> None:
    await _confirmed_external_without_interaction(
        workspace_id=workspace_id,
        marker=marker,
        member_token=member_token,
    )
    await _seed_message(
        workspace_id=workspace_id,
        marker=marker,
        external_id="unconfirmed-external",
        sender="unconfirmed@ignored.test",
        recipient=_owner_email(marker),
        occurred_at=datetime(2026, 7, 13, 14, 0, tzinfo=timezone.utc),
        raw_body="UNCONFIRMED_BODY_MUST_NOT_APPEAR",
    )


def _assert_safe_capabilities(report: dict) -> None:
    assert report["capabilities"] == {
        "provider_calls": False,
        "external_write": False,
        "llm_used": False,
    }
    serialized = json.dumps(report, sort_keys=True)
    assert "confirmed@customer.test" not in serialized
    assert "unconfirmed@ignored.test" not in serialized
    assert "PRIVATE_BACKFILL_BODY_MUST_NOT_APPEAR" not in serialized
    assert "UNCONFIRMED_BODY_MUST_NOT_APPEAR" not in serialized


async def test_company_world_backfill_dry_run_is_aggregate_only_and_writes_nothing(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        _member, member_token = await _add_member(
            workspace_id=workspace_id,
            marker=marker,
            suffix="member",
            role="member",
        )
        await _seed_backfill_scenario(
            workspace_id=workspace_id,
            marker=marker,
            member_token=member_token,
        )

        async with AsyncSessionLocal() as session:
            report = await backfill_company_world(
                session,
                workspace_id,
                apply=False,
            )
            await session.commit()

        assert report["workspace_id"] == str(workspace_id)
        assert report["mode"] == "dry_run"
        assert report["counts"] == {
            "memberships_seen": 2,
            "confirmed_external_people_seen": 1,
            "people_proposed": 2,
            "organizations_proposed": 0,
            "affiliations_proposed": 0,
            "interactions_proposed": 1,
            "people_written": 0,
            "organizations_written": 0,
            "affiliations_written": 0,
            "interactions_written": 0,
            "conflicts": 0,
        }
        assert report["writes_performed"] is False
        assert isinstance(report["warnings"], list)
        _assert_safe_capabilities(report)

        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Person)
                    .where(Person.workspace_id == workspace_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Interaction)
                    .where(Interaction.workspace_id == workspace_id)
                )
                == 0
            )
    finally:
        await _cleanup(marker)


async def test_company_world_backfill_apply_is_idempotent_and_skips_unconfirmed_people(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        _member, member_token = await _add_member(
            workspace_id=workspace_id,
            marker=marker,
            suffix="member",
            role="member",
        )
        await _seed_backfill_scenario(
            workspace_id=workspace_id,
            marker=marker,
            member_token=member_token,
        )

        async with AsyncSessionLocal() as session:
            first = await backfill_company_world(session, workspace_id, apply=True)
            await session.commit()
        assert first["mode"] == "apply"
        assert first["counts"]["people_written"] == 2
        assert first["counts"]["organizations_written"] == 0
        assert first["counts"]["affiliations_written"] == 0
        assert first["counts"]["interactions_written"] == 1
        assert first["counts"]["conflicts"] == 0
        assert first["writes_performed"] is True
        _assert_safe_capabilities(first)

        async with AsyncSessionLocal() as session:
            second = await backfill_company_world(session, workspace_id, apply=True)
            await session.commit()
        assert second["mode"] == "apply"
        assert second["counts"]["memberships_seen"] == 2
        assert second["counts"]["confirmed_external_people_seen"] == 1
        assert second["counts"]["people_proposed"] == 0
        assert second["counts"]["interactions_proposed"] == 0
        assert second["counts"]["people_written"] == 0
        assert second["counts"]["interactions_written"] == 0
        assert second["counts"]["conflicts"] == 0
        assert second["writes_performed"] is False
        _assert_safe_capabilities(second)

        async with AsyncSessionLocal() as session:
            people = list(
                (
                    await session.execute(select(Person).where(Person.workspace_id == workspace_id))
                ).scalars()
            )
            assert len(people) == 3
            assert sum(person.origin == "membership" for person in people) == 2
            assert sum(person.origin == "founder_confirmation" for person in people) == 1
            assert all(person.normalized_email != "unconfirmed@ignored.test" for person in people)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Interaction)
                    .where(Interaction.workspace_id == workspace_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Organization)
                    .where(Organization.workspace_id == workspace_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Affiliation)
                    .where(Affiliation.workspace_id == workspace_id)
                )
                == 1
            )
    finally:
        await _cleanup(marker)


async def test_confirmation_and_apply_backfill_are_workspace_serialized(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        _member, member_token = await _add_member(
            workspace_id=workspace_id,
            marker=marker,
            suffix="member",
            role="member",
        )
        await _seed_message(
            workspace_id=workspace_id,
            marker=marker,
            external_id="concurrent-confirmation",
            sender="concurrent-contact@gmail.com",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 15, 0, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "concurrent-contact@gmail.com")

        async def apply_backfill() -> dict:
            async with AsyncSessionLocal() as session:
                report = await backfill_company_world(session, workspace_id, apply=True)
                await session.commit()
                return report

        confirmation, report = await asyncio.gather(
            _resolve(
                workspace_id=workspace_id,
                token=member_token,
                payload={
                    "candidate_type": "external_person",
                    "candidate_key": candidate["key"],
                    "candidate_version": candidate["candidate_version"],
                    "decision": "confirmed",
                    "idempotency_key": str(uuid4()),
                },
            ),
            apply_backfill(),
        )

        assert confirmation.status_code in {200, 201}, confirmation.text
        assert report["mode"] == "apply"
        assert report["counts"]["people_written"] == 2
        assert report["counts"]["conflicts"] == 0

        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Person)
                    .where(Person.workspace_id == workspace_id)
                )
                == 3
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Interaction)
                    .where(Interaction.workspace_id == workspace_id)
                )
                == 1
            )
    finally:
        await _cleanup(marker)
