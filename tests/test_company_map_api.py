from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import SourceRecord
from app.db.identity_models import (
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    UserSession,
    Workspace,
)
from app.main import app
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
    return f"company-map-{marker}{suffix}@founderos.test"


def _bootstrap_payload(marker: str, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": _owner_email(marker, suffix),
        "owner_name": f"Founder {suffix or 'A'}",
        "workspace_name": f"Company World {marker}{suffix}",
        "workspace_slug": f"company-world-{marker}{suffix}",
    }


async def _bootstrap_workspace(marker: str, suffix: str = "") -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json=_bootstrap_payload(marker, suffix),
        )
    assert response.status_code == 201, response.text
    return response.json()


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"company-world-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"company-map-{marker}%"))
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _get_company_map(*, workspace_id: str, owner_email: str) -> tuple[int, dict]:
    async with _async_client() as client:
        response = await client.get(
            f"/api/v1/workspaces/{workspace_id}/company-map",
            headers=_headers(),
            params={"owner_email": owner_email},
        )
    return response.status_code, response.json()


async def test_company_map_empty_state_has_workspace_and_membership_evidence(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        status_code, body = await _get_company_map(
            workspace_id=created["workspace"]["id"],
            owner_email=_owner_email(marker),
        )

        assert status_code == 200
        assert body["mode"] == "evidence_backed_projection"
        assert body["source"] == "workspace_and_company_brain_projection"
        assert body["company"]["name"] == _bootstrap_payload(marker)["workspace_name"]
        assert body["company"]["source_refs"][0]["record_type"] == "workspace"
        assert body["summary"] == {
            "internal_people": 1,
            "confirmed_external_people": 0,
            "confirmed_organizations": 0,
            "external_contacts_in_window": 0,
            "organizations_in_window": 0,
            "touchpoints_in_window": 0,
        }
        assert body["window"] == {
            "gmail_messages_available": 0,
            "gmail_messages_considered": 0,
            "message_limit": 100,
            "truncated": False,
            "order": "newest_first",
        }
        assert body["people"]["internal"][0]["role"] == "owner"
        assert body["people"]["internal"][0]["source_refs"][0]["record_type"] == ("membership")
        assert body["people"]["external_candidates"] == []
        assert body["organizations"] == []
        assert body["touchpoints"] == []
        assert body["capabilities"] == {
            "read_only": True,
            "can_resolve": True,
            "required_role": "member",
            "provider_calls": False,
            "llm_used": False,
        }
    finally:
        await _cleanup(marker)


async def test_company_map_projects_people_organizations_and_touchpoints(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        owner_email = _owner_email(marker)
        first_at = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
        second_at = first_at + timedelta(hours=3)

        async with AsyncSessionLocal() as session:
            teammate = User(
                email=f"company-map-{marker}-teammate@founderos.test",
                name="Product Lead",
            )
            session.add(teammate)
            await session.flush()
            session.add(
                Membership(
                    workspace_id=workspace_id,
                    user_id=teammate.id,
                    role="member",
                )
            )
            session.add_all(
                [
                    SourceRecord(
                        workspace_id=workspace_id,
                        provider="gmail",
                        external_id=f"gmail-outbound-{marker}",
                        record_type="message",
                        source_url="https://mail.google.com/mail/u/0/#sent/outbound",
                        payload={
                            "normalized_message": {
                                "message_id": f"gmail-outbound-{marker}",
                                "thread_id": f"thread-{marker}",
                                "subject": "Kickoff and next steps",
                                "from_address": owner_email,
                                "to_addresses": [
                                    "Buyer Person <buyer@acme.test>",
                                    "prospect@gmail.com",
                                ],
                                "source_url": ("https://mail.google.com/mail/u/0/#sent/outbound"),
                            },
                            "evidence_refs": [
                                {
                                    "kind": "gmail_message",
                                    "source": "gmail",
                                    "ref": f"gmail-outbound-{marker}",
                                }
                            ],
                            "raw_body": "PRIVATE_BODY_MUST_NOT_RENDER",
                        },
                        payload_hash=f"outbound-{marker}",
                        observed_at=first_at,
                        source_updated_at=first_at,
                    ),
                    SourceRecord(
                        workspace_id=workspace_id,
                        provider="gmail",
                        external_id=f"gmail-inbound-{marker}",
                        record_type="message",
                        source_url="https://mail.google.com/mail/u/0/#inbox/inbound",
                        payload={
                            "normalized_message": {
                                "message_id": f"gmail-inbound-{marker}",
                                "thread_id": f"thread-{marker}",
                                "subject": "Re: Kickoff and next steps",
                                "from_address": "Buyer Person <buyer@acme.test>",
                                "to_addresses": [owner_email],
                                "source_url": ("https://mail.google.com/mail/u/0/#inbox/inbound"),
                            },
                            "evidence_refs": [
                                {
                                    "kind": "gmail_message",
                                    "source": "gmail",
                                    "ref": f"gmail-inbound-{marker}",
                                }
                            ],
                        },
                        payload_hash=f"inbound-{marker}",
                        observed_at=second_at,
                        source_updated_at=second_at,
                    ),
                ]
            )
            await session.commit()

        status_code, body = await _get_company_map(
            workspace_id=str(workspace_id),
            owner_email=owner_email,
        )

        assert status_code == 200
        assert body["summary"] == {
            "internal_people": 2,
            "confirmed_external_people": 0,
            "confirmed_organizations": 0,
            "external_contacts_in_window": 2,
            "organizations_in_window": 1,
            "touchpoints_in_window": 2,
        }
        assert body["window"]["truncated"] is False
        buyer = next(
            row
            for row in body["people"]["external_candidates"]
            if row["email"] == "buyer@acme.test"
        )
        assert buyer["display_name"] == "Buyer Person"
        assert buyer["interaction_count"] == 2
        assert buyer["organization_key"] == "organization:acme.test"
        assert buyer["needs_founder_confirm"] is True
        assert len(buyer["source_refs"]) == 2

        generic = next(
            row
            for row in body["people"]["external_candidates"]
            if row["email"] == "prospect@gmail.com"
        )
        assert generic["organization_key"] is None

        organization = body["organizations"][0]
        assert len(organization["candidate_version"]) == 64
        assert body["organizations"] == [
            {
                "key": "organization:acme.test",
                "candidate_version": organization["candidate_version"],
                "domain": "acme.test",
                "name": None,
                "kind": "external_candidate",
                "people_count": 1,
                "interaction_count": 2,
                "last_interaction_at": second_at.isoformat().replace("+00:00", "Z"),
                "source_refs": buyer["source_refs"],
                "needs_founder_confirm": True,
            }
        ]
        assert {row["direction"] for row in body["touchpoints"]} == {
            "inbound",
            "outbound",
        }
        serialized = json.dumps(body, sort_keys=True)
        assert "PRIVATE_BODY_MUST_NOT_RENDER" not in serialized
    finally:
        await _cleanup(marker)


async def test_company_map_is_workspace_scoped(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        first = await _bootstrap_workspace(marker, "-a")
        second = await _bootstrap_workspace(marker, "-b")
        first_workspace_id = UUID(first["workspace"]["id"])
        now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add(
                SourceRecord(
                    workspace_id=first_workspace_id,
                    provider="gmail",
                    external_id=f"isolated-{marker}",
                    record_type="message",
                    payload={
                        "normalized_message": {
                            "message_id": f"isolated-{marker}",
                            "subject": "Workspace A only",
                            "from_address": "contact@isolated.test",
                            "to_addresses": [_owner_email(marker, "-a")],
                        }
                    },
                    payload_hash=f"isolated-{marker}",
                    observed_at=now,
                    source_updated_at=now,
                )
            )
            await session.commit()

        second_status, second_body = await _get_company_map(
            workspace_id=second["workspace"]["id"],
            owner_email=_owner_email(marker, "-b"),
        )
        assert second_status == 200
        assert second_body["summary"]["external_contacts_in_window"] == 0
        assert second_body["touchpoints"] == []

        wrong_owner_status, _wrong_owner_body = await _get_company_map(
            workspace_id=first["workspace"]["id"],
            owner_email=_owner_email(marker, "-b"),
        )
        assert wrong_owner_status == 404
    finally:
        await _cleanup(marker)


async def test_company_map_marks_the_bounded_message_window(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        owner_email = _owner_email(marker)
        started_at = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    SourceRecord(
                        workspace_id=workspace_id,
                        provider="gmail",
                        external_id=f"window-{marker}-{index}",
                        record_type="message",
                        payload={
                            "normalized_message": {
                                "message_id": f"window-{marker}-{index}",
                                "subject": f"Window message {index}",
                                "from_address": f"contact-{index}@customer.test",
                                "to_addresses": [owner_email],
                            }
                        },
                        payload_hash=f"window-{marker}-{index}",
                        observed_at=started_at + timedelta(minutes=index),
                        source_updated_at=started_at + timedelta(minutes=index),
                    )
                    for index in range(101)
                ]
            )
            await session.commit()

        status_code, body = await _get_company_map(
            workspace_id=str(workspace_id),
            owner_email=owner_email,
        )

        assert status_code == 200
        assert body["window"] == {
            "gmail_messages_available": 101,
            "gmail_messages_considered": 100,
            "message_limit": 100,
            "truncated": True,
            "order": "newest_first",
        }
        assert body["summary"]["external_contacts_in_window"] == 100
        assert body["summary"]["organizations_in_window"] == 1
        assert body["summary"]["touchpoints_in_window"] == 100
        serialized = json.dumps(body, sort_keys=True)
        assert "contact-100@customer.test" in serialized
        assert "contact-0@customer.test" not in serialized
    finally:
        await _cleanup(marker)


async def test_company_map_allows_read_only_viewer_access(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        member_email = f"company-map-{marker}-member@founderos.test"
        viewer_email = f"company-map-{marker}-viewer@founderos.test"
        async with AsyncSessionLocal() as session:
            member = User(email=member_email, name="Member")
            viewer = User(email=viewer_email, name="Viewer")
            session.add_all([member, viewer])
            await session.flush()
            session.add_all(
                [
                    Membership(
                        workspace_id=workspace_id,
                        user_id=member.id,
                        role=MEMBERSHIP_ROLE_MEMBER,
                    ),
                    Membership(
                        workspace_id=workspace_id,
                        user_id=viewer.id,
                        role=MEMBERSHIP_ROLE_VIEWER,
                    ),
                ]
            )
            viewer_token, _stored_session = await create_session(session, viewer.id)
            await session.commit()

        member_status, _member_body = await _get_company_map(
            workspace_id=str(workspace_id),
            owner_email=member_email,
        )
        async with _async_client() as client:
            client.cookies.set(settings.session_cookie_name, viewer_token)
            viewer_response = await client.get(f"/api/v1/workspaces/{workspace_id}/company-map")
        viewer_status = viewer_response.status_code
        viewer_body = viewer_response.json()

        assert member_status == 200
        assert viewer_status == 200
        assert viewer_body["summary"]["internal_people"] == 3
        assert viewer_body["capabilities"]["read_only"] is True
    finally:
        await _cleanup(marker)
