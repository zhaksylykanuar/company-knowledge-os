from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import SOURCE_RECORD_PROVIDER_JIRA, TASK_PROVIDER_JIRA, SourceRecord, Task
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_JIRA,
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
        user = User(email=f"jira-{marker}@example.test", name="Jira Owner")
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Jira {marker}",
            slug=f"jira-{marker}",
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
        user = User(email=f"jira-{marker}-viewer@example.test", name="Jira Viewer")
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
                    select(Workspace.id).where(Workspace.slug.like(f"jira-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"jira-{marker}%@example.test"))
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(delete(Task).where(Task.workspace_id.in_(workspace_ids)))
            await session.execute(
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(delete(Membership).where(Membership.workspace_id.in_(workspace_ids)))
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def test_import_jira_issues_persists_canonical_tasks_without_provider_writes(
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
                provider=INTEGRATION_PROVIDER_JIRA,
                status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                display_name="Jira Cloud",
                external_account_id="jira-site",
                encrypted_access_token="SHOULD_NOT_LEAK_JIRA_TOKEN",
            )
            session.add(connection)
            await session.commit()
            connection_id = connection.id

        async with _client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace.id}/jira/issues/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "connection_id": str(connection_id),
                    "issues": [
                        {
                            "key": "fos-123",
                            "summary": "Review private beta onboarding",
                            "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                            "priority": {"name": "High"},
                            "url": "https://jira.example/browse/FOS-123",
                            "updated": "2026-07-06T10:00:00Z",
                            "fields": {"duedate": "2026-07-12"},
                            "api_token": "SHOULD_NOT_LEAK_RAW_TOKEN",
                        },
                        {
                            "key": "FOS-124",
                            "fields": {
                                "summary": "Ship local Jira import",
                                "status": {"name": "Done", "statusCategory": {"key": "done"}},
                            },
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
            "tasks_created": 2,
            "tasks_updated": 0,
        }
        assert body["boundary"] == {
            "external_writes": False,
            "llm": False,
            "provider_calls": False,
            "reads_secrets": False,
            "sync_started": False,
        }
        assert body["issues"][0]["key"] == "FOS-123"
        assert body["issues"][0]["evidence_refs"][0]["ref"] == "FOS-123"
        assert "SHOULD_NOT_LEAK" not in str(body)

        async with AsyncSessionLocal() as session:
            tasks = list(
                (
                    await session.execute(
                        select(Task)
                        .where(Task.workspace_id == workspace.id)
                        .where(Task.source_provider == TASK_PROVIDER_JIRA)
                    )
                ).scalars()
            )
            source_records = list(
                (
                    await session.execute(
                        select(SourceRecord)
                        .where(SourceRecord.workspace_id == workspace.id)
                        .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_JIRA)
                    )
                ).scalars()
            )

        assert {task.external_id for task in tasks} == {"FOS-123", "FOS-124"}
        assert {record.external_id for record in source_records} == {"FOS-123", "FOS-124"}
        assert all(record.connection_id == connection_id for record in source_records)
        assert "SHOULD_NOT_LEAK" not in str([record.payload for record in source_records])

    finally:
        await _cleanup(marker)


async def test_jira_import_is_idempotent_and_lists_local_issues(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        payload = {
            "issues": [
                {
                    "key": "FOS-200",
                    "summary": "Initial summary",
                    "status": "Open",
                    "url": "https://jira.example/browse/FOS-200",
                }
            ]
        }
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/jira/issues/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json=payload,
            )
            updated = await client.post(
                f"/api/v1/workspaces/{workspace.id}/jira/issues/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"issues": [{**payload["issues"][0], "summary": "Updated summary"}]},
            )
            listed = await client.get(
                f"/api/v1/workspaces/{workspace.id}/jira/issues",
                headers=_headers(),
                params={"owner_email": user.email},
            )

        assert created.status_code == 201
        assert updated.status_code == 201
        assert updated.json()["counts"]["tasks_updated"] == 1
        assert listed.status_code == 200
        body = listed.json()
        assert body["counts"] == {"done": 0, "not_done": 1, "total": 1}
        assert body["issues"][0]["key"] == "FOS-200"
        assert body["issues"][0]["title"] == "Updated summary"
        assert body["issues"][0]["source_url"] == "https://jira.example/browse/FOS-200"

        async with AsyncSessionLocal() as session:
            task_count = await session.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.workspace_id == workspace.id)
                .where(Task.source_provider == TASK_PROVIDER_JIRA)
            )
        assert task_count == 1

    finally:
        await _cleanup(marker)


async def test_jira_import_reports_invalid_entries_and_requires_admin_role(
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
                f"/api/v1/workspaces/{workspace.id}/jira/issues/import",
                headers=_headers(),
                params={"owner_email": viewer.email},
                json={"issues": [{"key": "FOS-300", "summary": "Viewer try"}]},
            )
            partial = await client.post(
                f"/api/v1/workspaces/{workspace.id}/jira/issues/import",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "issues": [
                        {"summary": "Missing key"},
                        {"key": "FOS-301", "summary": "Valid issue"},
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
            {"index": 0, "reason": "jira issue key is required, e.g. FOS-123"}
        ]

    finally:
        await _cleanup(marker)
