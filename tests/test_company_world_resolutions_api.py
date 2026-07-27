from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import SourceRecord
from app.db.company_world_models import (
    Affiliation,
    CompanyWorldResolution,
    Interaction,
    Organization,
    Person,
)
from app.db.identity_models import Membership, User, UserSession, Workspace
from app.db.memory_models import (
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED,
    CompanyMemoryEvent,
    CompanyMemoryEventStream,
)
from app.main import app
from app.services import company_world_confirmation_service
from app.services.session_service import create_session


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _owner_email(marker: str, suffix: str = "") -> str:
    return f"company-world-resolution-{marker}{suffix}@founderos.test"


async def _bootstrap_workspace(marker: str, suffix: str = "") -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json={
                "owner_email": _owner_email(marker, suffix),
                "owner_name": f"Founder {suffix or 'A'}",
                "workspace_name": f"Resolution Test {marker}{suffix}",
                "workspace_slug": f"resolution-test-{marker}{suffix}",
            },
        )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_member(
    *, workspace_id: UUID, marker: str, suffix: str, role: str
) -> tuple[User, str]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"company-world-resolution-{marker}-{suffix}@founderos.test",
            name=f"{role.title()} {suffix}",
        )
        session.add(user)
        await session.flush()
        session.add(Membership(workspace_id=workspace_id, user_id=user.id, role=role))
        token, _stored_session = await create_session(session, user.id)
        await session.commit()
        await session.refresh(user)
        return user, token


async def _seed_message(
    *,
    workspace_id: UUID,
    marker: str,
    external_id: str,
    sender: str,
    recipient: str,
    occurred_at: datetime,
    raw_body: str | None = None,
) -> UUID:
    async with AsyncSessionLocal() as session:
        source_record = SourceRecord(
            workspace_id=workspace_id,
            provider="gmail",
            external_id=f"{external_id}-{marker}",
            record_type="message",
            source_url=f"https://mail.google.com/mail/u/0/#inbox/{external_id}",
            payload={
                "normalized_message": {
                    "message_id": f"{external_id}-{marker}",
                    "thread_id": f"thread-{marker}",
                    "subject": f"Conversation {external_id}",
                    "from_address": sender,
                    "to_addresses": [recipient],
                },
                "evidence_refs": [
                    {
                        "kind": "gmail_message",
                        "source": "gmail",
                        "ref": f"{external_id}-{marker}",
                    }
                ],
                "raw_body": raw_body,
            },
            payload_hash=f"hash-{external_id}-{marker}",
            observed_at=occurred_at,
            source_updated_at=occurred_at,
        )
        session.add(source_record)
        await session.commit()
        await session.refresh(source_record)
        return source_record.id


async def _company_map(
    *, workspace_id: UUID, token: str | None = None, owner_email: str | None = None
) -> dict:
    async with _async_client() as client:
        if token is not None:
            client.cookies.set(settings.session_cookie_name, token)
        response = await client.get(
            f"/api/v1/workspaces/{workspace_id}/company-map",
            headers={} if token is not None else _headers(),
            params={} if owner_email is None else {"owner_email": owner_email},
        )
    assert response.status_code == 200, response.text
    return response.json()


async def _resolve(*, workspace_id: UUID, token: str, payload: dict) -> Response:
    async with _async_client() as client:
        client.cookies.set(settings.session_cookie_name, token)
        return await client.post(
            f"/api/v1/workspaces/{workspace_id}/company-map/resolutions",
            json=payload,
        )


def _person_candidate(company_map: dict, email: str) -> dict:
    return next(
        candidate
        for candidate in company_map["people"]["external_candidates"]
        if candidate["email"] == email
    )


def _organization_candidate(company_map: dict, domain: str) -> dict:
    return next(
        candidate for candidate in company_map["organizations"] if candidate["domain"] == domain
    )


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"resolution-test-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"company-world-resolution-{marker}%"))
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
        if user_ids:
            await session.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def test_member_confirmation_reuses_confirmed_organization_and_is_idempotent(
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
        owner_email = _owner_email(marker)
        first_at = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)
        source_record_ids = {
            await _seed_message(
                workspace_id=workspace_id,
                marker=marker,
                external_id="buyer-inbound",
                sender="Buyer Person <buyer@acme.test>",
                recipient=owner_email,
                occurred_at=first_at,
                raw_body="PRIVATE_CONFIRMATION_BODY_MUST_NOT_PERSIST",
            ),
            await _seed_message(
                workspace_id=workspace_id,
                marker=marker,
                external_id="buyer-outbound",
                sender=owner_email,
                recipient="Buyer Person <buyer@acme.test>",
                occurred_at=first_at + timedelta(hours=1),
            ),
        }
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "buyer@acme.test")
        organization_candidate = _organization_candidate(company_map, "acme.test")
        organization_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "organization",
                "candidate_key": organization_candidate["key"],
                "candidate_version": organization_candidate["candidate_version"],
                "decision": "confirmed",
                "idempotency_key": str(uuid4()),
                "organization_name": "Acme",
                "organization_relationship_kind": "customer",
            },
        )
        assert organization_response.status_code in {200, 201}, organization_response.text
        confirmed_organization_id = organization_response.json()["organization_id"]
        idempotency_key = str(uuid4())
        payload = {
            "candidate_type": "external_person",
            "candidate_key": candidate["key"],
            "candidate_version": candidate["candidate_version"],
            "decision": "confirmed",
            "idempotency_key": idempotency_key,
            "display_name": "Buyer Person",
            "relationship_type": "employee",
            "role_title": "Procurement Lead",
        }

        first_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload=payload,
        )
        assert first_response.status_code in {200, 201}, first_response.text
        first_body = first_response.json()
        assert first_body["resolution"]["candidate_type"] == "external_person"
        assert first_body["resolution"]["candidate_key"] == candidate["key"]
        assert first_body["resolution"]["decision"] == "confirmed"
        assert first_body["person_id"] is not None
        assert first_body["organization_id"] == confirmed_organization_id
        assert first_body["affiliation_id"] is not None
        assert first_body["interaction_count"] == 2
        assert first_body["replayed"] is False
        assert first_body["capabilities"] == {
            "provider_calls": False,
            "external_write": False,
            "llm_used": False,
        }
        assert "PRIVATE_CONFIRMATION_BODY_MUST_NOT_PERSIST" not in json.dumps(
            first_body, sort_keys=True
        )

        replay_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload=payload,
        )
        assert replay_response.status_code in {200, 201}, replay_response.text
        replay_body = replay_response.json()
        assert replay_body["resolution"]["id"] == first_body["resolution"]["id"]
        assert replay_body["person_id"] == first_body["person_id"]
        assert replay_body["organization_id"] == first_body["organization_id"]
        assert replay_body["affiliation_id"] == first_body["affiliation_id"]
        assert replay_body["replayed"] is True

        same_decision_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={**payload, "idempotency_key": str(uuid4())},
        )
        assert same_decision_response.status_code in {200, 201}
        assert same_decision_response.json()["person_id"] == first_body["person_id"]
        assert same_decision_response.json()["replayed"] is True

        conflict_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={**payload, "display_name": "Different Name"},
        )
        assert conflict_response.status_code == 409

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
            interactions = list(
                (
                    await session.execute(
                        select(Interaction).where(Interaction.workspace_id == workspace_id)
                    )
                ).scalars()
            )
            assert len(interactions) == 2
            assert {row.source_record_id for row in interactions} == source_record_ids
            assert {
                "raw_body",
                "body",
                "snippet",
                "payload",
            }.isdisjoint(Interaction.__table__.columns.keys())
            assert "PRIVATE_CONFIRMATION_BODY_MUST_NOT_PERSIST" not in json.dumps(
                [{"subject": row.subject, "source_url": row.source_url} for row in interactions],
                sort_keys=True,
            )
            memory_events = list(
                (
                    await session.execute(
                        select(CompanyMemoryEvent)
                        .where(CompanyMemoryEvent.workspace_id == workspace_id)
                        .order_by(CompanyMemoryEvent.workspace_sequence.asc())
                    )
                ).scalars()
            )
            assert [event.event_type for event in memory_events] == [
                COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED,
                COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED,
            ]
            assert "PRIVATE_CONFIRMATION_BODY_MUST_NOT_PERSIST" not in json.dumps(
                [event.evidence_refs for event in memory_events],
                sort_keys=True,
            )
    finally:
        await _cleanup(marker)


async def test_concurrent_identical_confirm_reuses_one_durable_result(
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
        source_record_id = await _seed_message(
            workspace_id=workspace_id,
            marker=marker,
            external_id="concurrent-identical-confirm",
            sender="concurrent-identical@gmail.com",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 9, 30, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "concurrent-identical@gmail.com")
        payload = {
            "candidate_type": "external_person",
            "candidate_key": candidate["key"],
            "candidate_version": candidate["candidate_version"],
            "decision": "confirmed",
            "idempotency_key": str(uuid4()),
            "display_name": "Concurrent Contact",
        }

        original_workspace_lock = company_world_confirmation_service.lock_company_world_workspace
        both_requests_arrived = asyncio.Event()
        arrival_count = 0

        async def synchronized_workspace_lock(*, session, workspace_id) -> None:
            nonlocal arrival_count
            arrival_count += 1
            if arrival_count == 2:
                both_requests_arrived.set()
            await asyncio.wait_for(both_requests_arrived.wait(), timeout=5)
            await original_workspace_lock(session=session, workspace_id=workspace_id)

        monkeypatch.setattr(
            company_world_confirmation_service,
            "lock_company_world_workspace",
            synchronized_workspace_lock,
        )

        responses = await asyncio.gather(
            _resolve(workspace_id=workspace_id, token=member_token, payload=payload),
            _resolve(workspace_id=workspace_id, token=member_token, payload=payload),
        )
        assert all(response.status_code in {200, 201} for response in responses)
        bodies = [response.json() for response in responses]
        assert arrival_count == 2
        assert {body["resolution"]["id"] for body in bodies} == {bodies[0]["resolution"]["id"]}
        assert {body["person_id"] for body in bodies} == {bodies[0]["person_id"]}
        assert bodies[0]["person_id"] is not None
        assert sorted(body["replayed"] for body in bodies) == [False, True]
        assert {body["interaction_count"] for body in bodies} == {1}

        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CompanyWorldResolution)
                    .where(CompanyWorldResolution.workspace_id == workspace_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Person)
                    .where(Person.workspace_id == workspace_id)
                )
                == 1
            )
            interactions = list(
                (
                    await session.execute(
                        select(Interaction).where(Interaction.workspace_id == workspace_id)
                    )
                ).scalars()
            )
            assert len(interactions) == 1
            assert interactions[0].source_record_id == source_record_id
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Organization)
                    .where(Organization.workspace_id == workspace_id)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Affiliation)
                    .where(Affiliation.workspace_id == workspace_id)
                )
                == 0
            )
            memory_events = list(
                (
                    await session.execute(
                        select(CompanyMemoryEvent).where(
                            CompanyMemoryEvent.workspace_id == workspace_id
                        )
                    )
                ).scalars()
            )
            assert len(memory_events) == 1
            assert memory_events[0].workspace_sequence == 1
            assert (
                await session.scalar(
                    select(CompanyMemoryEventStream.last_sequence).where(
                        CompanyMemoryEventStream.workspace_id == workspace_id
                    )
                )
                == 1
            )
    finally:
        await _cleanup(marker)


async def test_resolution_requires_member_role_and_hides_cross_workspace_candidates(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        first = await _bootstrap_workspace(marker, "-a")
        second = await _bootstrap_workspace(marker, "-b")
        first_workspace_id = UUID(first["workspace"]["id"])
        second_workspace_id = UUID(second["workspace"]["id"])
        _viewer, viewer_token = await _add_member(
            workspace_id=first_workspace_id,
            marker=marker,
            suffix="viewer",
            role="viewer",
        )
        _outsider, outsider_token = await _add_member(
            workspace_id=second_workspace_id,
            marker=marker,
            suffix="outsider",
            role="member",
        )
        await _seed_message(
            workspace_id=first_workspace_id,
            marker=marker,
            external_id="isolated",
            sender="contact@isolated.test",
            recipient=_owner_email(marker, "-a"),
            occurred_at=datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
        )
        company_map = await _company_map(
            workspace_id=first_workspace_id,
            owner_email=_owner_email(marker, "-a"),
        )
        candidate = _person_candidate(company_map, "contact@isolated.test")
        payload = {
            "candidate_type": "external_person",
            "candidate_key": candidate["key"],
            "candidate_version": candidate["candidate_version"],
            "decision": "confirmed",
            "idempotency_key": str(uuid4()),
        }

        viewer_response = await _resolve(
            workspace_id=first_workspace_id,
            token=viewer_token,
            payload=payload,
        )
        assert viewer_response.status_code == 403

        outsider_response = await _resolve(
            workspace_id=first_workspace_id,
            token=outsider_token,
            payload=payload,
        )
        assert outsider_response.status_code == 404
    finally:
        await _cleanup(marker)


async def test_resolution_rejects_missing_stale_and_client_forged_candidates(
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
            external_id="stale",
            sender="candidate@stale.test",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 11, 0, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "candidate@stale.test")
        base_payload = {
            "candidate_type": "external_person",
            "candidate_key": candidate["key"],
            "candidate_version": candidate["candidate_version"],
            "decision": "confirmed",
            "idempotency_key": str(uuid4()),
        }

        missing_version = dict(base_payload)
        missing_version.pop("candidate_version")
        assert (
            await _resolve(
                workspace_id=workspace_id,
                token=member_token,
                payload=missing_version,
            )
        ).status_code == 422

        stale_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={**base_payload, "candidate_version": "0" * 64},
        )
        assert stale_response.status_code == 409

        missing_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                **base_payload,
                "candidate_key": "external_person:missing",
                "idempotency_key": str(uuid4()),
            },
        )
        assert missing_response.status_code == 404

        forged_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                **base_payload,
                "email": "forged@attacker.test",
                "evidence_refs": [{"source_record_id": str(uuid4())}],
            },
        )
        assert forged_response.status_code == 422

        organization_fields_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                **base_payload,
                "organization_name": "Injected Organization",
                "organization_relationship_kind": "customer",
            },
        )
        assert organization_fields_response.status_code == 422

        role_without_relationship_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={**base_payload, "role_title": "Decision maker"},
        )
        assert role_without_relationship_response.status_code == 422
    finally:
        await _cleanup(marker)


async def test_unresolved_organization_blocks_person_confirmation(monkeypatch) -> None:
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
            external_id="unresolved-organization",
            sender="person@unresolved.test",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 11, 30, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        person_candidate = _person_candidate(company_map, "person@unresolved.test")

        response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "external_person",
                "candidate_key": person_candidate["key"],
                "candidate_version": person_candidate["candidate_version"],
                "decision": "confirmed",
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code == 409
        assert "organization candidate must be resolved" in response.json()["detail"]

        async with AsyncSessionLocal() as session:
            for model in (Person, Organization, Affiliation, Interaction):
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.workspace_id == workspace_id)
                    )
                    == 0
                )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CompanyWorldResolution)
                    .where(CompanyWorldResolution.workspace_id == workspace_id)
                )
                == 0
            )
    finally:
        await _cleanup(marker)


async def test_dismissed_organization_allows_standalone_person_confirmation(
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
            external_id="dismissed-organization",
            sender="person@dismissed-org.test",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 11, 45, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        person_candidate = _person_candidate(company_map, "person@dismissed-org.test")
        organization_candidate = _organization_candidate(company_map, "dismissed-org.test")

        organization_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "organization",
                "candidate_key": organization_candidate["key"],
                "candidate_version": organization_candidate["candidate_version"],
                "decision": "dismissed",
                "idempotency_key": str(uuid4()),
            },
        )
        assert organization_response.status_code in {200, 201}

        person_response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "external_person",
                "candidate_key": person_candidate["key"],
                "candidate_version": person_candidate["candidate_version"],
                "decision": "confirmed",
                "idempotency_key": str(uuid4()),
                "display_name": "Standalone Person",
            },
        )
        assert person_response.status_code in {200, 201}, person_response.text
        body = person_response.json()
        assert body["person_id"] is not None
        assert body["organization_id"] is None
        assert body["affiliation_id"] is None
        assert body["interaction_count"] == 1

        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Organization)
                    .where(Organization.workspace_id == workspace_id)
                )
                == 0
            )
            interaction = await session.scalar(
                select(Interaction).where(Interaction.workspace_id == workspace_id)
            )
            assert interaction is not None
            assert interaction.organization_id is None
    finally:
        await _cleanup(marker)


async def test_candidate_version_rejects_changed_payload_with_same_source_id(
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
        source_record_id = await _seed_message(
            workspace_id=workspace_id,
            marker=marker,
            external_id="same-source-stale",
            sender="Old Name <same-source@gmail.com>",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 11, 50, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "same-source@gmail.com")

        async with AsyncSessionLocal() as session:
            source_record = await session.get(SourceRecord, source_record_id)
            assert source_record is not None
            normalized_message = dict(source_record.payload["normalized_message"])
            normalized_message["from_address"] = "New Name <same-source@gmail.com>"
            source_record.payload = {
                **source_record.payload,
                "normalized_message": normalized_message,
            }
            source_record.payload_hash = f"changed-{marker}"
            await session.commit()

        response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "external_person",
                "candidate_key": candidate["key"],
                "candidate_version": candidate["candidate_version"],
                "decision": "confirmed",
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code == 409

        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Person)
                    .where(Person.workspace_id == workspace_id)
                )
                == 0
            )
    finally:
        await _cleanup(marker)


async def test_confirmation_materializes_only_visible_snapshot_and_russian_fallback(
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
        started_at = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            records = []
            for index in range(101):
                normalized_message = {
                    "message_id": f"snapshot-{marker}-{index}",
                    "from_address": "snapshot-contact@gmail.com",
                    "to_addresses": [_owner_email(marker)],
                }
                if index == 0:
                    normalized_message["subject"] = "OUTSIDE SNAPSHOT MUST NOT PERSIST"
                elif index != 100:
                    normalized_message["subject"] = f"Snapshot message {index}"
                records.append(
                    SourceRecord(
                        workspace_id=workspace_id,
                        provider="gmail",
                        external_id=f"snapshot-{marker}-{index}",
                        record_type="message",
                        payload={"normalized_message": normalized_message},
                        payload_hash=f"snapshot-hash-{marker}-{index}",
                        observed_at=started_at + timedelta(minutes=index),
                        source_updated_at=started_at + timedelta(minutes=index),
                    )
                )
            session.add_all(records)
            await session.commit()
            oldest_record_id = records[0].id

        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "snapshot-contact@gmail.com")
        assert candidate["interaction_count"] == 100
        assert any(touchpoint["subject"] == "Без темы" for touchpoint in company_map["touchpoints"])

        response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "external_person",
                "candidate_key": candidate["key"],
                "candidate_version": candidate["candidate_version"],
                "decision": "confirmed",
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code in {200, 201}, response.text
        assert response.json()["interaction_count"] == 100

        async with AsyncSessionLocal() as session:
            interactions = list(
                (
                    await session.execute(
                        select(Interaction).where(Interaction.workspace_id == workspace_id)
                    )
                ).scalars()
            )
            assert len(interactions) == 100
            assert oldest_record_id not in {
                interaction.source_record_id for interaction in interactions
            }
            assert "Без темы" in {interaction.subject for interaction in interactions}
            assert "OUTSIDE SNAPSHOT MUST NOT PERSIST" not in {
                interaction.subject for interaction in interactions
            }
    finally:
        await _cleanup(marker)


async def test_dismissal_persists_only_resolution_and_hides_candidate(
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
            external_id="dismissed",
            sender="not-relevant@vendor.test",
            recipient=_owner_email(marker),
            occurred_at=datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
        )
        company_map = await _company_map(workspace_id=workspace_id, token=member_token)
        candidate = _person_candidate(company_map, "not-relevant@vendor.test")

        response = await _resolve(
            workspace_id=workspace_id,
            token=member_token,
            payload={
                "candidate_type": "external_person",
                "candidate_key": candidate["key"],
                "candidate_version": candidate["candidate_version"],
                "decision": "dismissed",
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code in {200, 201}, response.text
        body = response.json()
        assert body["resolution"]["decision"] == "dismissed"
        assert body["person_id"] is None
        assert body["organization_id"] is None
        assert body["affiliation_id"] is None
        assert body["interaction_count"] == 0

        refreshed = await _company_map(workspace_id=workspace_id, token=member_token)
        assert all(
            row["key"] != candidate["key"] for row in refreshed["people"]["external_candidates"]
        )

        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CompanyWorldResolution)
                    .where(CompanyWorldResolution.workspace_id == workspace_id)
                )
                == 1
            )
            for model in (Person, Organization, Affiliation, Interaction):
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.workspace_id == workspace_id)
                    )
                    == 0
                )
    finally:
        await _cleanup(marker)
