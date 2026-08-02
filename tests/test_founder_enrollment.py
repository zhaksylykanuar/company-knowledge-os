"""Invite-only founder enrollment and its atomic security boundaries."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, select, update

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    FounderEnrollmentInvite,
    Membership,
    User,
    UserSession,
    Workspace,
)
from app.main import app
from app.services.founder_enrollment_service import (
    FOUNDER_ENROLLMENT_CONFLICT,
    FOUNDER_INVITE_REVOCATION_FAILURE,
    INVALID_FOUNDER_INVITE,
    MAX_FOUNDER_INVITE_TTL_HOURS,
    FounderInviteRevocationError,
    create_founder_invite,
    hash_founder_invite_token,
)
from app.services.identity_service import (
    create_membership,
    create_user,
    create_workspace,
)
from scripts.create_founder_invite import _create as _create_founder_invite_cli
from scripts.create_founder_invite import _invite_url
from scripts.revoke_founder_invite import _revoke

PASSWORD = "enrollment-test-password"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _payload(marker: str, token: str) -> dict[str, str]:
    return {
        "token": token,
        "email": f"founder-{marker}@example.test",
        "name": "Test Founder",
        "password": PASSWORD,
        "workspace_name": f"Company {marker}",
        "workspace_slug": f"company-{marker}",
    }


async def _create_invite(*, ttl_hours: int = 72) -> tuple[str, UUID]:
    async with AsyncSessionLocal() as session:
        created = await create_founder_invite(session, ttl_hours=ttl_hours)
        values = (created.raw_token, created.row.id)
        await session.commit()
        return values


async def _seed_identity(*, email: str, workspace_slug: str) -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as session:
        user = await create_user(session, email=email, name="Existing Founder")
        workspace = await create_workspace(
            session,
            name="Existing Company",
            slug=workspace_slug,
            created_by_user_id=user.id,
        )
        await create_membership(
            session,
            workspace_id=workspace.id,
            user_id=user.id,
            role=MEMBERSHIP_ROLE_OWNER,
        )
        values = (user.id, workspace.id)
        await session.commit()
        return values


async def _cleanup(
    *,
    emails: list[str] | None = None,
    workspace_slugs: list[str] | None = None,
    invite_ids: list[UUID] | None = None,
) -> None:
    emails = emails or []
    workspace_slugs = workspace_slugs or []
    invite_ids = invite_ids or []
    async with AsyncSessionLocal() as session:
        user_ids = list(
            (
                await session.scalars(
                    select(User.id).where(User.email.in_(emails))
                    if emails
                    else select(User.id).where(False)
                )
            ).all()
        )
        workspace_ids = list(
            (
                await session.scalars(
                    select(Workspace.id).where(Workspace.slug.in_(workspace_slugs))
                    if workspace_slugs
                    else select(Workspace.id).where(False)
                )
            ).all()
        )
        if invite_ids:
            await session.execute(
                delete(FounderEnrollmentInvite).where(
                    FounderEnrollmentInvite.id.in_(invite_ids)
                )
            )
        if user_ids:
            await session.execute(
                delete(UserSession).where(UserSession.user_id.in_(user_ids))
            )
        membership_conditions = []
        if user_ids:
            membership_conditions.append(Membership.user_id.in_(user_ids))
        if workspace_ids:
            membership_conditions.append(Membership.workspace_id.in_(workspace_ids))
        for condition in membership_conditions:
            await session.execute(delete(Membership).where(condition))
        if workspace_ids:
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _post_enrollment(payload: dict[str, str]) -> Response:
    async with _client() as client:
        return await client.post("/api/v1/auth/enroll", json=payload)


async def test_invite_creation_persists_only_hash_and_expiry() -> None:
    raw_token, invite_id = await _create_invite(ttl_hours=12)
    try:
        async with AsyncSessionLocal() as session:
            row = await session.get(FounderEnrollmentInvite, invite_id)
        assert row is not None
        assert row.token_hash == hash_founder_invite_token(raw_token)
        assert row.token_hash != raw_token
        assert len(row.token_hash) == 64
        assert row.expires_at > datetime.now(timezone.utc)
        assert row.consumed_at is None
        assert row.revoked_at is None
    finally:
        await _cleanup(invite_ids=[invite_id])


async def test_invite_ttl_is_capped_at_seven_days() -> None:
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError, match="between 1 and 168"):
            await create_founder_invite(
                session,
                ttl_hours=MAX_FOUNDER_INVITE_TTL_HOURS + 1,
            )
        await session.rollback()


@pytest.mark.parametrize(
    "base_url",
    [
        "https://founderos.example.test",
        "http://127.0.0.1:3000/app",
    ],
)
def test_invite_url_keeps_token_in_fragment_not_http_query(base_url: str) -> None:
    raw_token = "test-only-opaque-token"
    invite_url = _invite_url(base_url, raw_token)
    parsed = urlsplit(invite_url)
    assert parsed.path.endswith("/start")
    assert parsed.query == ""
    assert parse_qs(parsed.fragment) == {"token": [raw_token]}


@pytest.mark.parametrize(
    "base_url",
    [
        "http://founderos.example.test",
        "http://localhost:3000",
        "http://[::1]:3000",
        "ftp://founderos.example.test",
        "https://operator:secret@founderos.example.test",
    ],
)
def test_invite_url_rejects_insecure_remote_or_embedded_credentials(
    base_url: str,
) -> None:
    with pytest.raises(ValueError):
        _invite_url(base_url, "test-only-opaque-token")


async def test_invite_cli_rejects_invalid_base_url_before_persisting() -> None:
    async with AsyncSessionLocal() as session:
        before = await session.scalar(
            select(func.count()).select_from(FounderEnrollmentInvite)
        )

    with pytest.raises(ValueError):
        await _create_founder_invite_cli(
            base_url="http://founderos.example.test",
            ttl_hours=72,
        )

    async with AsyncSessionLocal() as session:
        after = await session.scalar(
            select(func.count()).select_from(FounderEnrollmentInvite)
        )
    assert after == before


async def test_enroll_creates_complete_identity_consumes_invite_and_sets_cookie() -> None:
    marker = uuid4().hex[:12]
    raw_token, invite_id = await _create_invite()
    payload = _payload(marker, raw_token)
    try:
        async with _client() as client:
            response = await client.post("/api/v1/auth/enroll", json=payload)
            me_response = await client.get("/api/v1/auth/me")

        assert response.status_code == 201
        assert response.json()["user"]["email"] == payload["email"]
        assert response.json()["workspace"]["slug"] == payload["workspace_slug"]
        assert response.json()["workspace"]["role"] == MEMBERSHIP_ROLE_OWNER
        assert settings.session_cookie_name in response.cookies
        assert me_response.status_code == 200

        async with AsyncSessionLocal() as session:
            user = await session.scalar(select(User).where(User.email == payload["email"]))
            workspace = await session.scalar(
                select(Workspace).where(Workspace.slug == payload["workspace_slug"])
            )
            invite = await session.get(FounderEnrollmentInvite, invite_id)
            assert user is not None and workspace is not None and invite is not None
            membership = await session.scalar(
                select(Membership)
                .where(Membership.user_id == user.id)
                .where(Membership.workspace_id == workspace.id)
            )
            session_count = await session.scalar(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.user_id == user.id)
            )
        assert membership is not None and membership.role == MEMBERSHIP_ROLE_OWNER
        assert session_count == 1
        assert invite.consumed_at is not None
        assert invite.consumed_by_user_id == user.id
        assert invite.consumed_workspace_id == workspace.id
    finally:
        await _cleanup(
            emails=[payload["email"]],
            workspace_slugs=[payload["workspace_slug"]],
            invite_ids=[invite_id],
        )


async def test_enroll_sanitizes_and_truncates_oversized_user_agent() -> None:
    marker = uuid4().hex[:12]
    raw_token, invite_id = await _create_invite()
    payload = _payload(marker, raw_token)
    try:
        oversized_user_agent = "agent-" + ("x" * 600)
        async with _client() as client:
            response = await client.post(
                "/api/v1/auth/enroll",
                json=payload,
                headers={"user-agent": oversized_user_agent},
            )
        assert response.status_code == 201

        async with AsyncSessionLocal() as session:
            user = await session.scalar(select(User).where(User.email == payload["email"]))
            assert user is not None
            user_session = await session.scalar(
                select(UserSession).where(UserSession.user_id == user.id)
            )
        assert user_session is not None
        assert user_session.user_agent == oversized_user_agent[:512]
        assert len(user_session.user_agent) == 512
    finally:
        await _cleanup(
            emails=[payload["email"]],
            workspace_slugs=[payload["workspace_slug"]],
            invite_ids=[invite_id],
        )


@pytest.mark.parametrize("case", ["malformed", "expired", "revoked"])
async def test_invalid_invites_are_generic_and_create_nothing(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = uuid4().hex[:12]
    invite_ids: list[UUID] = []
    if case == "malformed":
        raw_token = "not-an-issued-founder-invite"
    else:
        raw_token, invite_id = await _create_invite()
        invite_ids.append(invite_id)
        if case == "expired":
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(FounderEnrollmentInvite)
                    .where(FounderEnrollmentInvite.id == invite_id)
                    .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
                )
                await session.commit()
        else:
            revoke_result = await _revoke(invite_id)
            assert revoke_result["invite_id"] == str(invite_id)
            assert revoke_result["revoked_at"]
    payload = _payload(marker, raw_token)
    monkeypatch.setattr(
        "app.services.founder_enrollment_service.hash_password",
        lambda _password: pytest.fail("invalid invite must not run Argon2"),
    )
    try:
        response = await _post_enrollment(payload)
        assert response.status_code == 400
        assert response.json()["detail"] == INVALID_FOUNDER_INVITE
        assert settings.session_cookie_name not in response.cookies

        async with AsyncSessionLocal() as session:
            user_count = await session.scalar(
                select(func.count()).select_from(User).where(User.email == payload["email"])
            )
            workspace_count = await session.scalar(
                select(func.count())
                .select_from(Workspace)
                .where(Workspace.slug == payload["workspace_slug"])
            )
        assert user_count == 0
        assert workspace_count == 0
    finally:
        await _cleanup(
            emails=[payload["email"]],
            workspace_slugs=[payload["workspace_slug"]],
            invite_ids=invite_ids,
        )


async def test_consumed_invite_cannot_be_revoked() -> None:
    marker = uuid4().hex[:12]
    raw_token, invite_id = await _create_invite()
    payload = _payload(marker, raw_token)
    try:
        response = await _post_enrollment(payload)
        assert response.status_code == 201
        with pytest.raises(
            FounderInviteRevocationError,
            match=FOUNDER_INVITE_REVOCATION_FAILURE,
        ):
            await _revoke(invite_id)
        async with AsyncSessionLocal() as session:
            invite = await session.get(FounderEnrollmentInvite, invite_id)
        assert invite is not None
        assert invite.consumed_at is not None
        assert invite.revoked_at is None
    finally:
        await _cleanup(
            emails=[payload["email"]],
            workspace_slugs=[payload["workspace_slug"]],
            invite_ids=[invite_id],
        )


async def test_reused_invite_is_generic_and_second_identity_is_not_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_marker = uuid4().hex[:12]
    second_marker = uuid4().hex[:12]
    raw_token, invite_id = await _create_invite()
    first = _payload(first_marker, raw_token)
    second = _payload(second_marker, raw_token)
    try:
        first_response = await _post_enrollment(first)
        monkeypatch.setattr(
            "app.services.founder_enrollment_service.hash_password",
            lambda _password: pytest.fail("reused invite must not run Argon2"),
        )
        second_response = await _post_enrollment(second)
        assert first_response.status_code == 201
        assert second_response.status_code == 400
        assert second_response.json()["detail"] == INVALID_FOUNDER_INVITE

        async with AsyncSessionLocal() as session:
            second_user = await session.scalar(
                select(User).where(User.email == second["email"])
            )
            second_workspace = await session.scalar(
                select(Workspace).where(Workspace.slug == second["workspace_slug"])
            )
        assert second_user is None
        assert second_workspace is None
    finally:
        await _cleanup(
            emails=[first["email"], second["email"]],
            workspace_slugs=[first["workspace_slug"], second["workspace_slug"]],
            invite_ids=[invite_id],
        )


@pytest.mark.parametrize("conflict_kind", ["email", "slug"])
async def test_conflict_is_409_atomic_and_does_not_consume_invite(
    conflict_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = uuid4().hex[:12]
    existing_email = f"existing-{marker}@example.test"
    existing_slug = f"existing-company-{marker}"
    await _seed_identity(email=existing_email, workspace_slug=existing_slug)
    raw_token, invite_id = await _create_invite()
    payload = _payload(marker, raw_token)
    if conflict_kind == "email":
        payload["email"] = existing_email
    else:
        payload["workspace_slug"] = existing_slug
    monkeypatch.setattr(
        "app.services.founder_enrollment_service.hash_password",
        lambda _password: pytest.fail("identity conflict must not run Argon2"),
    )
    try:
        response = await _post_enrollment(payload)
        assert response.status_code == 409
        assert response.json()["detail"] == FOUNDER_ENROLLMENT_CONFLICT

        async with AsyncSessionLocal() as session:
            invite = await session.get(FounderEnrollmentInvite, invite_id)
            candidate_user = await session.scalar(
                select(User).where(User.email == f"founder-{marker}@example.test")
            )
            candidate_workspace = await session.scalar(
                select(Workspace).where(Workspace.slug == f"company-{marker}")
            )
        assert invite is not None and invite.consumed_at is None
        if conflict_kind == "email":
            assert candidate_workspace is None
        else:
            assert candidate_user is None
    finally:
        await _cleanup(
            emails=[existing_email, f"founder-{marker}@example.test"],
            workspace_slugs=[existing_slug, f"company-{marker}"],
            invite_ids=[invite_id],
        )


async def test_concurrent_double_consume_allows_exactly_one_enrollment() -> None:
    marker_a = uuid4().hex[:12]
    marker_b = uuid4().hex[:12]
    raw_token, invite_id = await _create_invite()
    payload_a = _payload(marker_a, raw_token)
    payload_b = _payload(marker_b, raw_token)
    try:
        responses = await asyncio.gather(
            _post_enrollment(payload_a),
            _post_enrollment(payload_b),
        )
        assert sorted(response.status_code for response in responses) == [201, 400]
        failure = next(response for response in responses if response.status_code == 400)
        assert failure.json()["detail"] == INVALID_FOUNDER_INVITE

        async with AsyncSessionLocal() as session:
            created_users = await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.email.in_([payload_a["email"], payload_b["email"]]))
            )
            created_workspaces = await session.scalar(
                select(func.count())
                .select_from(Workspace)
                .where(
                    Workspace.slug.in_(
                        [payload_a["workspace_slug"], payload_b["workspace_slug"]]
                    )
                )
            )
            invite = await session.get(FounderEnrollmentInvite, invite_id)
        assert created_users == 1
        assert created_workspaces == 1
        assert invite is not None and invite.consumed_at is not None
    finally:
        await _cleanup(
            emails=[payload_a["email"], payload_b["email"]],
            workspace_slugs=[payload_a["workspace_slug"], payload_b["workspace_slug"]],
            invite_ids=[invite_id],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("token", ""),
        ("token", "x" * 1025),
        ("email", "not-an-email"),
        ("password", "short"),
        ("workspace_name", "   "),
        ("workspace_slug", "Not valid / slug"),
    ],
)
async def test_enrollment_validates_identity_fields_without_consuming_invite(
    field: str,
    value: str,
) -> None:
    marker = uuid4().hex[:12]
    raw_token, invite_id = await _create_invite()
    payload = _payload(marker, raw_token)
    payload[field] = value
    try:
        response = await _post_enrollment(payload)
        assert response.status_code == 422
        async with AsyncSessionLocal() as session:
            invite = await session.get(FounderEnrollmentInvite, invite_id)
        assert invite is not None and invite.consumed_at is None
    finally:
        await _cleanup(
            emails=[f"founder-{marker}@example.test"],
            workspace_slugs=[f"company-{marker}"],
            invite_ids=[invite_id],
        )
