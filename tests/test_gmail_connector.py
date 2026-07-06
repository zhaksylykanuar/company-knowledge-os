from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GMAIL, SourceRecord
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GMAIL,
    IntegrationConnection,
)
from app.main import app


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace(marker: str) -> tuple[User, Workspace]:
    async with AsyncSessionLocal() as session:
        user = User(email=f"gmail-{marker}@example.test", name="Gmail Owner")
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Gmail {marker}",
            slug=f"gmail-{marker}",
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


async def _seed_viewer(workspace: Workspace, marker: str) -> User:
    async with AsyncSessionLocal() as session:
        user = User(email=f"gmail-{marker}-viewer@example.test", name="Gmail Viewer")
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MEMBERSHIP_ROLE_VIEWER,
            )
        )
        await session.commit()
        return user


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"gmail-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"gmail-{marker}%@example.test"))
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def test_import_gmail_messages_persists_source_records_without_raw_body_or_secrets(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            connection = IntegrationConnection(
                workspace_id=workspace.id,
                provider=INTEGRATION_PROVIDER_GMAIL,
                status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                display_name="Gmail",
                external_account_id="gmail-account",
                encrypted_access_token="SHOULD_NOT_LEAK_GMAIL_TOKEN",
            )
            session.add(connection)
            await session.commit()
            connection_id = connection.id

        async with _client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace.id}/gmail/messages/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "connection_id": str(connection_id),
                    "messages": [
                        {
                            "id": "msg-1",
                            "thread_id": "thread-1",
                            "subject": "Investor intro follow-up",
                            "snippet": "Following up on the intro call from yesterday.",
                            "from": {"email": "founder@example.test"},
                            "to": ["investor@example.test"],
                            "labels": ["INBOX", "UNREAD"],
                            "internal_date": "2026-07-06T10:00:00Z",
                            "url": "https://mail.google.com/mail/u/0/#inbox/msg-1",
                            "body": "RAW_BODY_SHOULD_NOT_BE_PERSISTED",
                            "api_token": "SHOULD_NOT_LEAK_RAW_TOKEN",
                        },
                        {
                            "message_id": "msg-2",
                            "subject": "Weekly ops digest",
                            "labels": ["INBOX"],
                        },
                    ],
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["counts"] == {
            "failed": 0,
            "imported": 2,
            "received": 2,
            "source_records_created": 2,
            "source_records_updated": 0,
        }
        assert body["boundary"] == {
            "external_writes": False,
            "llm": False,
            "provider_calls": False,
            "reads_secrets": False,
            "sync_started": False,
        }
        assert body["messages"][0]["message_id"] == "msg-1"
        assert body["messages"][0]["unread"] is True
        assert body["messages"][0]["evidence_refs"][0]["ref"] == "msg-1"
        assert "SHOULD_NOT_LEAK" not in str(body)
        assert "RAW_BODY_SHOULD_NOT_BE_PERSISTED" not in str(body)

        async with AsyncSessionLocal() as session:
            records = list(
                (
                    await session.execute(
                        select(SourceRecord)
                        .where(SourceRecord.workspace_id == workspace.id)
                        .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL)
                    )
                ).scalars()
            )

        assert {record.external_id for record in records} == {"msg-1", "msg-2"}
        assert all(record.connection_id == connection_id for record in records)
        serialized = str([record.payload for record in records])
        assert "SHOULD_NOT_LEAK" not in serialized
        assert "RAW_BODY_SHOULD_NOT_BE_PERSISTED" not in serialized

    finally:
        await _cleanup(marker)


async def test_gmail_import_is_idempotent_and_lists_local_messages(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        payload = {
            "messages": [
                {
                    "id": "msg-100",
                    "subject": "Initial subject",
                    "labels": ["INBOX", "UNREAD"],
                    "url": "https://mail.google.com/mail/u/0/#inbox/msg-100",
                }
            ]
        }
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/gmail/messages/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json=payload,
            )
            updated = await client.post(
                f"/api/v1/workspaces/{workspace.id}/gmail/messages/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "messages": [
                        {**payload["messages"][0], "subject": "Updated subject", "labels": ["INBOX"]}
                    ]
                },
            )
            listed = await client.get(
                f"/api/v1/workspaces/{workspace.id}/gmail/messages",
                headers=_headers(),
                params={"owner_email": user.email},
            )

        assert created.status_code == 201
        assert updated.status_code == 201
        assert updated.json()["counts"]["source_records_updated"] == 1
        assert listed.status_code == 200
        body = listed.json()
        assert body["counts"] == {"read": 1, "total": 1, "unread": 0}
        assert body["messages"][0]["message_id"] == "msg-100"
        assert body["messages"][0]["subject"] == "Updated subject"
        assert body["messages"][0]["unread"] is False

        async with AsyncSessionLocal() as session:
            record_count = await session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(SourceRecord.workspace_id == workspace.id)
                .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GMAIL)
            )
        assert record_count == 1

    finally:
        await _cleanup(marker)


async def test_gmail_import_reports_invalid_entries_and_requires_admin_role(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        viewer = await _seed_viewer(workspace, marker)

        async with _client() as client:
            forbidden = await client.post(
                f"/api/v1/workspaces/{workspace.id}/gmail/messages/import",
                headers=_headers(),
                params={"owner_email": viewer.email},
                json={"messages": [{"id": "msg-403", "subject": "Viewer try"}]},
            )
            partial = await client.post(
                f"/api/v1/workspaces/{workspace.id}/gmail/messages/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "messages": [
                        {"subject": "Missing id"},
                        {"id": "msg-301", "subject": "Valid message"},
                    ]
                },
            )

        assert forbidden.status_code == 403
        assert partial.status_code == 201
        body = partial.json()
        assert body["counts"]["received"] == 2
        assert body["counts"]["imported"] == 1
        assert body["counts"]["failed"] == 1
        assert body["failures"] == [
            {"index": 0, "reason": "gmail message id is required"}
        ]

    finally:
        await _cleanup(marker)
