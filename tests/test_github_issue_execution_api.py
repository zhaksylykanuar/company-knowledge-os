from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_issue_execution_service as github_issue_execution_service
import app.services.github_execution_result_sync_service as github_execution_result_sync_service
import app.api.actions as actions_api
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.action_models import (
    ACTION_CREATED_BY_USER,
    ACTION_EXECUTION_STATUS_FAILED,
    ACTION_EXECUTION_STATUS_SUCCEEDED,
    ACTION_EXECUTION_STATUS_UNCERTAIN,
    ACTION_EXECUTION_EVENT_REPOSITORY_NOT_ALLOWED,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ACTION_TYPE_INTERNAL_TODO,
    ActionExecution,
    ActionExecutionEvent,
    ActionProposal,
)
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import Repository, SourceRecord, Task
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    INTEGRATION_CONNECTION_STATUS_REVOKED,
    INTEGRATION_PROVIDER_GITHUB,
    INTEGRATION_PROVIDER_JIRA,
    IntegrationConnection,
    SyncJob,
)
from app.main import app
from app.services.github_issue_client import GitHubIssueClientError
from app.services.secret_encryption import encrypt_secret

PLAIN_EXECUTION_TOKEN = "execution-test-token-value"


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "secret_encryption_key", SecretStr("test-encryption-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")
    monkeypatch.setattr(settings, "enable_real_connectors", True)
    monkeypatch.setattr(settings, "enable_write_actions", True)
    monkeypatch.setattr(settings, "github_write_allowed_repos", "qtwin-io/founderos-api")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _block_live_github_issue_client(monkeypatch):
    async def fail_create_issue(**_kwargs):
        raise AssertionError("GitHub issue client must be mocked in tests")

    async def fail_get_issue(**_kwargs):
        raise AssertionError("GitHub issue read client must be mocked in tests")

    async def fail_list_issues(**_kwargs):
        raise AssertionError("GitHub issue list client must be mocked in tests")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)
    monkeypatch.setattr(github_execution_result_sync_service, "get_issue", fail_get_issue)
    monkeypatch.setattr(
        github_execution_result_sync_service,
        "list_issues",
        fail_list_issues,
    )


def _bootstrap_payload(marker: str, *, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"issue-action-{marker}{suffix}@example.test",
        "owner_name": "Issue Action Owner",
        "workspace_name": f"Issue Action {marker}{suffix}",
        "workspace_slug": f"issue-action-{marker}{suffix}",
    }


def _proposal_payload(**overrides) -> dict:
    payload = {
        "target_provider": ACTION_TARGET_PROVIDER_GITHUB,
        "action_type": ACTION_TYPE_CREATE_GITHUB_ISSUE,
        "title": "Create GitHub issue",
        "description": "Approved issue creation proposal.",
        "payload": {
            "repository_full_name": "qtwin-io/founderos-api",
            "title": "FounderOS follow-up",
            "body": "Created through approved action execution.",
            "labels": ["founderos"],
            "assignees": ["founder"],
        },
        "evidence_refs": [
            {
                "kind": "repository",
                "source": "github_repository_read_api",
                "ref": "qtwin-io/founderos-api",
                "url": None,
            }
        ],
        "created_by": ACTION_CREATED_BY_USER,
    }
    payload.update(overrides)
    return payload


async def _cleanup_issue_action_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"issue-action-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"issue-action-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        proposal_ids: list[UUID] = []
        if workspace_ids:
            proposal_ids = list(
                (
                    await session.execute(
                        select(ActionProposal.id).where(
                            ActionProposal.workspace_id.in_(workspace_ids)
                        )
                    )
                ).scalars()
            )
            if proposal_ids:
                await session.execute(
                    delete(ActionExecutionEvent).where(
                        ActionExecutionEvent.action_proposal_id.in_(proposal_ids)
                    )
                )
                await session.execute(
                    delete(ActionExecution).where(
                        ActionExecution.action_proposal_id.in_(proposal_ids)
                    )
                )
            await session.execute(
                delete(Task).where(Task.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Repository).where(Repository.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(ActionProposal).where(
                    ActionProposal.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
        if workspace_ids:
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _bootstrap_workspace(marker: str, *, suffix: str = "") -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json=_bootstrap_payload(marker, suffix=suffix),
        )
    assert response.status_code == 201, response.text
    created = response.json()
    async with AsyncSessionLocal() as session:
        session.add(
            Repository(
                workspace_id=UUID(created["workspace"]["id"]),
                provider="github",
                external_id=f"repository-{marker}{suffix}",
                name="founderos-api",
                full_name="qtwin-io/founderos-api",
                visibility="private",
                archived=False,
                source_url="https://github.com/qtwin-io/founderos-api",
                repo_metadata={"fixture": "github_issue_execution"},
            )
        )
        await session.commit()
    return created


async def _add_workspace_user(
    workspace_id: str,
    marker: str,
    *,
    role: str,
    suffix: str,
) -> str:
    email = f"issue-action-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"Issue Action {role}")
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                workspace_id=UUID(workspace_id),
                user_id=user.id,
                role=role,
            )
        )
        await session.commit()
    return email


async def _create_connection(
    workspace_id: str,
    *,
    provider: str = INTEGRATION_PROVIDER_GITHUB,
    status: str = INTEGRATION_CONNECTION_STATUS_CONNECTED,
    encrypted_access_token: str | None = "encrypted",
) -> UUID:
    token = (
        encrypt_secret(PLAIN_EXECUTION_TOKEN)
        if encrypted_access_token == "encrypted"
        else encrypted_access_token
    )
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider=provider,
            status=status,
            display_name="Issue action connection",
            external_account_id=f"issue-action-{uuid4().hex}",
            encrypted_access_token=token,
            scopes=["issues:write"],
            provider_metadata={"connection_method": "test"},
        )
        session.add(connection)
        await session.commit()
        return connection.id


async def _post_proposal(
    workspace_id: str,
    owner_email: str,
    *,
    payload: dict | None = None,
) -> dict:
    async with _async_client() as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals",
            headers=_headers(),
            params={"owner_email": owner_email},
            json=payload if payload is not None else _proposal_payload(),
        )
    assert response.status_code == 201, response.text
    return response.json()["proposal"]


async def _approve_proposal(
    workspace_id: str,
    proposal: dict,
    owner_email: str,
) -> dict:
    async with _async_client() as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal['id']}/approve",
            headers=_headers(),
            params={"owner_email": owner_email},
            json={
                "idempotency_key": f"approve-{uuid4()}",
                "proposal_version": proposal["proposal_version"],
            },
        )
    assert response.status_code == 200, response.text
    return response.json()["proposal"]


async def _create_approved_proposal(
    workspace_id: str,
    owner_email: str,
    *,
    payload: dict | None = None,
) -> dict:
    proposal = await _post_proposal(workspace_id, owner_email, payload=payload)
    return await _approve_proposal(workspace_id, proposal, owner_email)


async def _seed_proposal(
    workspace_id: str,
    *,
    status: str = ACTION_PROPOSAL_STATUS_APPROVED,
    target_provider: str = ACTION_TARGET_PROVIDER_GITHUB,
    action_type: str = ACTION_TYPE_CREATE_GITHUB_ISSUE,
    payload: dict | None = None,
) -> UUID:
    async with AsyncSessionLocal() as session:
        proposal = ActionProposal(
            workspace_id=UUID(workspace_id),
            target_provider=target_provider,
            action_type=action_type,
            title="Seeded proposal",
            payload=payload if payload is not None else _proposal_payload()["payload"],
            status=status,
            evidence_refs=[],
            created_by=ACTION_CREATED_BY_USER,
        )
        session.add(proposal)
        await session.commit()
        return proposal.id


async def _execute_proposal(
    workspace_id: str,
    proposal_id: str | UUID,
    owner_email: str,
    *,
    connection_id: UUID | None,
    confirm_external_write: bool = True,
    idempotency_key: str | None = None,
):
    payload: dict = {
        "confirm_external_write": confirm_external_write,
        "idempotency_key": idempotency_key or f"execute-{uuid4()}",
    }
    if connection_id is not None:
        payload["connection_id"] = str(connection_id)
    async with _async_client() as client:
        return await client.post(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execute",
            headers=_headers(),
            params={"owner_email": owner_email},
            json=payload,
        )


async def _preview_execution(
    workspace_id: str,
    proposal_id: str | UUID,
    owner_email: str,
):
    async with _async_client() as client:
        return await client.get(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execution-preview",
            headers=_headers(),
            params={"owner_email": owner_email},
        )


async def _get_audit(
    workspace_id: str,
    proposal_id: str | UUID,
    owner_email: str,
):
    async with _async_client() as client:
        return await client.get(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/audit",
            headers=_headers(),
            params={"owner_email": owner_email},
        )


async def _sync_execution_result(
    workspace_id: str,
    proposal_id: str | UUID,
    owner_email: str,
    *,
    connection_id: UUID | None = None,
):
    payload: dict[str, str] = {}
    if connection_id is not None:
        payload["connection_id"] = str(connection_id)
    async with _async_client() as client:
        return await client.post(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result",
            headers=_headers(),
            params={"owner_email": owner_email},
            json=payload,
        )


async def _stored_proposal(proposal_id: str | UUID) -> ActionProposal:
    async with AsyncSessionLocal() as session:
        proposal = await session.scalar(
            select(ActionProposal).where(ActionProposal.id == UUID(str(proposal_id)))
        )
        assert proposal is not None
        return proposal


async def _stored_executions(proposal_id: str | UUID) -> list[ActionExecution]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(ActionExecution)
                .where(
                    ActionExecution.action_proposal_id == UUID(str(proposal_id))
                )
                .order_by(ActionExecution.created_at.asc(), ActionExecution.id.asc())
            )
        ).scalars()
        return list(rows)


async def _stored_user_id(email: str) -> UUID:
    async with AsyncSessionLocal() as session:
        user_id = await session.scalar(select(User.id).where(User.email == email))
        assert user_id is not None
        return user_id


async def _age_execution_provider_start(
    proposal_id: str | UUID,
    *,
    age: timedelta,
) -> None:
    async with AsyncSessionLocal() as session:
        execution = await session.scalar(
            select(ActionExecution).where(
                ActionExecution.action_proposal_id == UUID(str(proposal_id))
            )
        )
        assert execution is not None
        execution.started_at = datetime.now(timezone.utc) - age
        await session.commit()


async def _stored_execution_events(proposal_id: str | UUID) -> list[ActionExecutionEvent]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(ActionExecutionEvent)
                .where(ActionExecutionEvent.action_proposal_id == UUID(str(proposal_id)))
                .order_by(
                    ActionExecutionEvent.created_at.asc(),
                    ActionExecutionEvent.id.asc(),
                )
            )
        ).scalars()
        return sorted(
            [
                event
                for event in rows
                if str(event.event_type).startswith("execution_")
            ],
            key=_execution_event_sort_key,
        )


def _execution_event_sort_key(event: ActionExecutionEvent) -> tuple:
    order = {
        "execution_preview_generated": 10,
        "execution_preview_blocked": 11,
        "execution_unsupported": 12,
        "execution_confirmation_missing": 20,
        "execution_confirmation_received_but_disabled": 21,
        "execution_blocked": 22,
        "execution_repository_not_allowed": 23,
        "execution_confirmation_received": 30,
        "execution_claimed": 35,
        "execution_started": 40,
        "execution_succeeded": 50,
        "execution_failed": 51,
        "execution_outcome_uncertain": 52,
        "execution_duplicate_returned_existing_receipt": 60,
        "execution_result_sync_started": 70,
        "execution_reconciliation_pending": 71,
        "execution_outcome_reconciled": 71,
        "execution_write_not_observed": 71,
        "execution_result_synced": 72,
        "execution_result_sync_failed": 73,
    }
    return (event.created_at, order.get(event.event_type, 100), str(event.id))


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _mock_successful_github_issue(monkeypatch, calls: list[dict]) -> None:
    async def fake_create_issue(**kwargs):
        calls.append(kwargs)
        assert kwargs["access_token"] == PLAIN_EXECUTION_TOKEN
        assert "Created through approved action execution." in kwargs["body"]
        assert "<!-- founderos-execution:" in kwargs["body"]
        return _github_issue_response(kwargs)

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fake_create_issue)


def _github_issue_response(create_call: dict, *, number: int = 42) -> dict:
    return {
        "id": 987_654 + number,
        "number": number,
        "html_url": f"https://github.com/qtwin-io/founderos-api/issues/{number}",
        "url": (
            "https://api.github.com/repos/qtwin-io/"
            f"founderos-api/issues/{number}"
        ),
        "state": "open",
        "title": create_call["title"],
        "body": create_call.get("body"),
        "created_at": "2026-06-26T01:00:00Z",
        "updated_at": "2026-06-26T01:05:00Z",
        "token": PLAIN_EXECUTION_TOKEN,
    }


def _mock_read_github_issue(monkeypatch, calls: list[dict]) -> None:
    async def fake_get_issue(**kwargs):
        calls.append(kwargs)
        assert kwargs["access_token"] == PLAIN_EXECUTION_TOKEN
        assert kwargs["repository_full_name"] == "qtwin-io/founderos-api"
        assert kwargs["issue_number"] == 42
        return {
            "id": 987654,
            "number": 42,
            "html_url": "https://github.com/qtwin-io/founderos-api/issues/42",
            "url": "https://api.github.com/repos/qtwin-io/founderos-api/issues/42",
            "state": "open",
            "title": "FounderOS follow-up",
            "body": "private body should not be stored in canonical sync payload",
            "created_at": "2026-06-26T01:00:00Z",
            "updated_at": "2026-06-26T01:05:00Z",
            "token": PLAIN_EXECUTION_TOKEN,
        }

    monkeypatch.setattr(github_execution_result_sync_service, "get_issue", fake_get_issue)


async def test_execution_preview_is_dry_run_when_external_writes_disabled(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_write_actions", False)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)

        response = await _preview_execution(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "preview_ready"
        assert body["mode"] == "external_disabled"
        assert body["capabilities"] == {
            "dry_run": True,
            "local_approval": True,
            "external_execution": False,
            "live_provider_write": False,
            "requires_confirmation": True,
        }
        assert body["preview"]["provider"] == "github"
        assert body["preview"]["action"] == "create_github_issue"
        assert body["preview"]["repository"] == "qtwin-io/founderos-api"
        assert body["preview"]["title"] == "FounderOS follow-up"
        assert body["preview"]["evidence_refs"][0]["ref"] == "qtwin-io/founderos-api"
        assert body["audit"][0]["event_type"] == "action_proposal_approved_locally"
        assert body["audit"][0]["external_execution_enabled"] is False
        assert body["audit"][0]["confirmation_received"] is False
        assert body["audit"][0]["event_metadata"]["decision"] == "approved"
        assert body["audit"][1]["event_type"] == "execution_preview_generated"
        assert body["audit"][1]["event"] == "execution_preview_generated"
        assert body["audit"][1]["status"] == "recorded"
        assert body["audit"][1]["provider"] == "github"
        assert body["audit"][1]["external_execution_enabled"] is False
        assert body["audit"][1]["confirmation_received"] is False
        assert body["audit"][1]["external_result_id"] is None
        assert body["audit"][1]["external_result_url"] is None
        assert body["audit"][1]["event_metadata"]["evidence_refs_count"] == 1
        assert "Created through approved action execution" not in str(
            body["audit"][1]["event_metadata"]
        )
        assert body["warnings"] == [
            "Execution preview is dry-run only and does not call GitHub."
        ]
        assert await _stored_executions(proposal["id"]) == []
        events = await _stored_execution_events(proposal["id"])
        assert len(events) == 1
        assert events[0].event_type == "execution_preview_generated"

        repeated = await _preview_execution(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
        )
        assert repeated.status_code == 200, repeated.text
        assert len(await _stored_execution_events(proposal["id"])) == 1

        audit_response = await _get_audit(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
        )
        assert audit_response.status_code == 200, audit_response.text
        audit = audit_response.json()
        assert [event["event_type"] for event in audit["events"]] == [
            "action_proposal_approved_locally",
            "execution_preview_generated",
        ]
        assert audit["receipt"]["provider"] == "github"
        assert audit["receipt"]["provider_result"] == "none"
        assert audit["receipt"]["external_write_performed"] is False
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execution_preview_blocks_not_approved_proposal(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal_id = await _seed_proposal(
            created["workspace"]["id"],
            status=ACTION_PROPOSAL_STATUS_PROPOSED,
        )

        response = await _preview_execution(
            created["workspace"]["id"],
            proposal_id,
            owner_email,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "not_approved"
        assert body["preview"] is None
        assert body["capabilities"]["dry_run"] is False
        assert body["message"] == "action proposal is not approved"
        assert "Proposal has no evidence refs" in body["warnings"][1]
        assert body["audit"][0]["event_type"] == "execution_preview_blocked"
        assert body["audit"][0]["status"] == "blocked"
        assert body["audit"][0]["error_code"] == "action_proposal_is_not_approved"
        assert await _stored_executions(proposal_id) == []
        events = await _stored_execution_events(proposal_id)
        assert len(events) == 1
        assert events[0].event_type == "execution_preview_blocked"
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_audit_endpoint_returns_empty_trail_for_proposal_without_events(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal_id = await _seed_proposal(created["workspace"]["id"])

        response = await _get_audit(
            created["workspace"]["id"],
            proposal_id,
            owner_email,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["events"] == []
        assert body["receipt"] == {
            "provider": None,
            "action": None,
            "status": None,
            "external_execution_enabled": False,
            "confirmation_received": False,
            "external_result_id": None,
            "external_result_url": None,
            "external_write_performed": False,
            "provider_result": "none",
            "error_code": None,
            "error_message": None,
            "idempotency_key": None,
            "created_at": None,
            "updated_at": None,
        }
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_rejects_when_write_actions_disabled(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_write_actions", False)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "external execution is disabled"}
        assert await _stored_executions(proposal["id"]) == []
        events = await _stored_execution_events(proposal["id"])
        assert len(events) == 1
        assert (
            events[0].event_type
            == "execution_confirmation_received_but_disabled"
        )
        assert events[0].confirmation_received is True
        assert events[0].external_execution_enabled is False
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_fails_closed_when_real_connectors_disabled(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_real_connectors", False)
    await _cleanup_issue_action_fixture(marker)

    async def fail_execution_service(*_args, **_kwargs):
        raise AssertionError("provider execution service must stay disabled")

    monkeypatch.setattr(
        actions_api,
        "execute_approved_github_issue_action",
        fail_execution_service,
    )

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)

        preview = await _preview_execution(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["mode"] == "external_disabled"
        assert preview.json()["capabilities"]["external_execution"] is False
        assert preview.json()["capabilities"]["live_provider_write"] is False

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=uuid4(),
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "real provider connectors are disabled"}
        assert await _stored_executions(proposal["id"]) == []
    finally:
        await _cleanup_issue_action_fixture(marker)


@pytest.mark.parametrize("allowlist_value", [None, "", "   "])
async def test_execute_rejects_when_github_write_allowlist_missing(
    monkeypatch,
    allowlist_value: str | None,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_write_allowed_repos", allowlist_value)
    calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github write allowed repos are not configured"
        }
        assert calls == []
        assert await _stored_executions(proposal["id"]) == []
        events = await _stored_execution_events(proposal["id"])
        assert len(events) == 1
        assert events[0].event_type == ACTION_EXECUTION_EVENT_REPOSITORY_NOT_ALLOWED
        assert events[0].error_code == "github_write_allowed_repos_are_not_configured"
        assert events[0].event_metadata["repository_full_name"] == (
            "qtwin-io/founderos-api"
        )
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_rejects_github_issue_repo_not_in_write_allowlist(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(
        settings,
        "github_write_allowed_repos",
        "azhaks-cpo/founderos-smoke",
    )
    calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github repository is not allowed for live execution"
        }
        assert calls == []
        assert await _stored_executions(proposal["id"]) == []
        events = await _stored_execution_events(proposal["id"])
        assert len(events) == 1
        assert events[0].event_type == ACTION_EXECUTION_EVENT_REPOSITORY_NOT_ALLOWED
        assert events[0].error_code == (
            "github_repository_is_not_allowed_for_live_execution"
        )
        assert events[0].event_metadata["repository_full_name"] == (
            "qtwin-io/founderos-api"
        )
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_allows_github_issue_repo_in_write_allowlist(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(
        settings,
        "github_write_allowed_repos",
        "azhaks-cpo/founderos-smoke, qtwin-io/founderos-api",
    )
    calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 200, response.text
        assert calls[0]["repository_full_name"] == "qtwin-io/founderos-api"
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_succeeded",
        ]
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_revalidates_canonical_evidence_immediately_before_provider_call(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    provider_calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, provider_calls)
    original_validator = (
        github_issue_execution_service.validate_action_proposal_evidence
    )
    validation_count = 0

    async def invalidate_after_initial_validation(*args, **kwargs):
        nonlocal validation_count
        validation_count += 1
        resolved = await original_validator(*args, **kwargs)
        if validation_count == 1:
            async with AsyncSessionLocal() as mutation_session:
                repository = await mutation_session.scalar(
                    select(Repository).where(
                        Repository.workspace_id == kwargs["workspace_id"],
                        Repository.full_name == "qtwin-io/founderos-api",
                    )
                )
                assert repository is not None
                repository.archived = True
                await mutation_session.commit()
        return resolved

    monkeypatch.setattr(
        github_issue_execution_service,
        "validate_action_proposal_evidence",
        invalidate_after_initial_validation,
    )
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(
            created["workspace"]["id"],
            owner_email,
        )
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 409, response.text
        assert "missing, inactive, unsupported" in response.json()["detail"]
        assert validation_count == 2
        assert provider_calls == []
        executions = await _stored_executions(proposal["id"])
        assert len(executions) == 1
        assert executions[0].status == ACTION_EXECUTION_STATUS_FAILED
        assert (await _stored_proposal(proposal["id"])).status == (
            ACTION_PROPOSAL_STATUS_APPROVED
        )
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_failed",
        ]
        assert events[-1].error_code == "proposal_evidence_invalid"
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/execute",
                params={"owner_email": owner_email},
                json={
                    "connection_id": str(connection_id),
                    "confirm_external_write": True,
                },
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/execute",
                headers=_headers(),
                json={
                    "connection_id": str(connection_id),
                    "confirm_external_write": True,
                },
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_issue_action_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_OWNER, MEMBERSHIP_ROLE_ADMIN])
async def test_owner_admin_can_execute_approved_github_issue(
    monkeypatch,
    role: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        actor_email = owner_email
        if role == MEMBERSHIP_ROLE_ADMIN:
            actor_email = await _add_workspace_user(
                created["workspace"]["id"],
                marker,
                role=role,
                suffix=role,
            )
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            actor_email,
            connection_id=connection_id,
            idempotency_key="issue-action-test",
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["proposal"]["status"] == ACTION_PROPOSAL_STATUS_EXECUTED
        assert body["execution"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        actor_user_id = await _stored_user_id(actor_email)
        assert body["execution"]["workspace_id"] == created["workspace"]["id"]
        assert body["execution"]["requested_by_user_id"] == str(actor_user_id)
        assert body["execution"]["connection_id"] == str(connection_id)
        assert body["execution"]["client_idempotency_key"] == "issue-action-test"
        assert len(body["execution"]["request_hash"]) == 64
        assert body["execution"]["claimed_at"] is not None
        assert body["execution"]["reconciled_at"] is None
        assert body["execution"]["external_id"].endswith("/issues/42")
        assert body["execution"]["provider_response"]["number"] == 42
        assert "body" not in body["execution"]["provider_response"]
        assert "token" not in body["execution"]["provider_response"]
        assert body["receipt"]["provider"] == INTEGRATION_PROVIDER_GITHUB
        assert body["receipt"]["action"] == ACTION_TYPE_CREATE_GITHUB_ISSUE
        assert body["receipt"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert body["receipt"]["external_result_id"] == "42"
        assert (
            body["receipt"]["external_result_url"]
            == "https://github.com/qtwin-io/founderos-api/issues/42"
        )
        assert body["receipt"]["external_write_performed"] is True
        assert body["receipt"]["provider_result"] == "succeeded"
        assert body["receipt"]["idempotency_key"] == "issue-action-test"
        assert PLAIN_EXECUTION_TOKEN not in response.text
        assert body["is_live"] is True
        assert body["external_write_performed"] is True
        assert body["provider"] == INTEGRATION_PROVIDER_GITHUB
        assert calls[0]["repository_full_name"] == "qtwin-io/founderos-api"
        assert await _count(ActionExecution) >= 1
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_succeeded",
        ]
        assert all(event.actor == f"user:{actor_user_id}" for event in events)
        assert events[-1].external_result_id == "42"
        assert (
            events[-1].external_result_url
            == "https://github.com/qtwin-io/founderos-api/issues/42"
        )
        audit_response = await _get_audit(
            created["workspace"]["id"],
            proposal["id"],
            actor_email,
        )
        assert audit_response.status_code == 200, audit_response.text
        audit = audit_response.json()
        assert [event["event_type"] for event in audit["events"]] == [
            "action_proposal_approved_locally",
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_succeeded",
        ]
        assert audit["receipt"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert audit["receipt"]["provider_result"] == "succeeded"
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_sync_execution_result_reads_issue_into_product_state(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    write_calls: list[dict] = []
    read_calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, write_calls)
    _mock_read_github_issue(monkeypatch, read_calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        executed = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )
        assert executed.status_code == 200, executed.text

        synced = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert synced.status_code == 200, synced.text
        body = synced.json()
        assert body["synced"] is True
        assert body["status"] == "synced"
        assert body["provider"] == INTEGRATION_PROVIDER_GITHUB
        assert body["action"] == ACTION_TYPE_CREATE_GITHUB_ISSUE
        assert body["repository"] == "qtwin-io/founderos-api"
        assert body["issue"]["number"] == 42
        assert body["issue"]["state"] == "open"
        assert body["canonical"]["task_id"] is not None
        assert body["canonical"]["source_record_id"] is not None
        assert body["canonical"]["evidence_refs_count"] == 1
        assert body["counts"]["issues"] == 1
        assert "No external write occurred during sync." in body["warnings"]
        assert PLAIN_EXECUTION_TOKEN not in synced.text
        assert "private body should not be stored" not in synced.text
        assert len(write_calls) == 1
        assert len(read_calls) == 1

        async with AsyncSessionLocal() as session:
            task_count = await session.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.workspace_id == UUID(workspace_id))
            )
            source_record_count = await session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(SourceRecord.workspace_id == UUID(workspace_id))
            )
            task = await session.scalar(
                select(Task)
                .where(Task.workspace_id == UUID(workspace_id))
                .where(Task.source_provider == INTEGRATION_PROVIDER_GITHUB)
            )
            source_record = await session.scalar(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == UUID(workspace_id))
                .where(SourceRecord.provider == INTEGRATION_PROVIDER_GITHUB)
            )
        assert task_count == 1
        assert source_record_count == 1
        assert task is not None
        assert task.task_metadata["github_object_type"] == "issue"
        assert task.task_metadata["number"] == 42
        assert task.task_metadata["repository_full_name"] == "qtwin-io/founderos-api"
        assert source_record is not None
        assert PLAIN_EXECUTION_TOKEN not in str(source_record.payload)
        assert "private body should not be stored" not in str(source_record.payload)

        async with _async_client() as client:
            operational = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={"owner_email": owner_email, "state": "open"},
            )
            company_brain = await client.get(
                f"/api/v1/workspaces/{workspace_id}/company-brain",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            briefing = await client.post(
                f"/api/v1/workspaces/{workspace_id}/briefings/manual",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={"include_repository_inventory": False},
            )

        assert operational.status_code == 200, operational.text
        operational_body = operational.json()
        assert operational_body["counts"]["issues"] == 1
        assert operational_body["issues"][0]["number"] == 42
        assert operational_body["issues"][0]["repository_full_name"] == (
            "qtwin-io/founderos-api"
        )

        assert company_brain.status_code == 200, company_brain.text
        brain = company_brain.json()
        assert brain["summary"]["open_issues"] == 1
        assert brain["work"]["issues"][0]["number"] == 42
        assert brain["work"]["issues"][0]["source_refs"]

        assert briefing.status_code == 200, briefing.text
        briefing_body = briefing.json()["briefing"]
        assert briefing_body["signals"]["github"]["latest_sync_job_status"] == "succeeded"
        normalization_item = next(
            item
            for item in briefing_body["items"]
            if item["id"] == "github-normalization"
        )
        assert "issues=1" in normalization_item["summary"]
        assert normalization_item["evidence_refs"]

        repeated = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )
        assert repeated.status_code == 200, repeated.text
        assert len(write_calls) == 1
        assert len(read_calls) == 2
        async with AsyncSessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Task)
                    .where(Task.workspace_id == UUID(workspace_id))
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(SourceRecord)
                    .where(SourceRecord.workspace_id == UUID(workspace_id))
                )
                == 1
            )

        audit_response = await _get_audit(workspace_id, proposal["id"], owner_email)
        assert audit_response.status_code == 200, audit_response.text
        event_types = [event["event_type"] for event in audit_response.json()["events"]]
        assert event_types == [
            "action_proposal_approved_locally",
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_succeeded",
            "execution_result_sync_started",
            "execution_result_synced",
        ]
        assert audit_response.json()["receipt"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert audit_response.json()["receipt"]["external_write_performed"] is True
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_sync_execution_result_fails_closed_when_real_connectors_disabled(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_real_connectors", False)
    monkeypatch.setattr(
        github_execution_result_sync_service,
        "decrypt_secret",
        lambda _value: (_ for _ in ()).throw(
            AssertionError("token decrypt must stay disabled")
        ),
    )
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)

        response = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=uuid4(),
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "real provider connectors are disabled"}
        assert await _stored_executions(proposal["id"]) == []
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_sync_execution_result_requires_executed_successful_proposal(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        response = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "action proposal is not executed"}

        executed_without_receipt = await _seed_proposal(
            workspace_id,
            status=ACTION_PROPOSAL_STATUS_EXECUTED,
        )
        receipt_response = await _sync_execution_result(
            workspace_id,
            executed_without_receipt,
            owner_email,
            connection_id=connection_id,
        )

        assert receipt_response.status_code == 409
        assert receipt_response.json() == {
            "detail": "successful execution receipt is required"
        }
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_sync_execution_result_records_read_failure_without_write(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    write_calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, write_calls)

    async def fail_get_issue(**_kwargs):
        raise GitHubIssueClientError("github issue read request failed: not found")

    monkeypatch.setattr(github_execution_result_sync_service, "get_issue", fail_get_issue)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        executed = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )
        assert executed.status_code == 200, executed.text

        response = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 502
        assert response.json() == {"detail": "github issue read failed"}
        assert len(write_calls) == 1
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_succeeded",
            "execution_result_sync_started",
            "execution_result_sync_failed",
        ]
        assert events[-1].error_code == "provider_read_failed"
        assert PLAIN_EXECUTION_TOKEN not in events[-1].message
        assert PLAIN_EXECUTION_TOKEN not in str(events[-1].event_metadata)
    finally:
        await _cleanup_issue_action_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER])
async def test_member_viewer_cannot_execute(monkeypatch, role: str) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        actor_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=role,
            suffix=role,
        )
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            actor_email,
            connection_id=connection_id,
        )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_rejects_missing_confirmation_or_connection(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        missing_confirm = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            confirm_external_write=False,
        )
        missing_connection = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=None,
        )

        assert missing_confirm.status_code == 400
        assert missing_confirm.json() == {
            "detail": "confirm_external_write must be true"
        }
        assert missing_connection.status_code == 422
        assert await _stored_executions(proposal["id"]) == []
        events = await _stored_execution_events(proposal["id"])
        assert len(events) == 1
        assert events[0].event_type == "execution_confirmation_missing"
        assert events[0].confirmation_received is False
        assert events[0].external_execution_enabled is True
    finally:
        await _cleanup_issue_action_fixture(marker)


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        ({"title": "Missing repository"}, "repository_full_name is required"),
        (
            {"repository_full_name": "not-a-repo", "title": "Bad repo"},
            "repository_full_name must look like owner/repo",
        ),
        (
            {"repository_full_name": "qtwin-io/founderos-api"},
            "title is required",
        ),
        (
            {
                "repository_full_name": "qtwin-io/founderos-api",
                "title": "Bad labels",
                "labels": "bug",
            },
            "labels must be a list of strings",
        ),
        (
            {
                "repository_full_name": "qtwin-io/founderos-api",
                "title": "Bad payload",
                "nested": {"api_key": "placeholder"},
            },
            "payload contains secret-like key: api_key",
        ),
    ],
)
async def test_execute_rejects_invalid_issue_payload(
    monkeypatch,
    payload: dict,
    expected_detail: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    async def fail_create_issue(**_kwargs):
        raise AssertionError("GitHub client should not be called")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal_id = await _seed_proposal(created["workspace"]["id"], payload=payload)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal_id,
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 400
        assert response.json() == {"detail": expected_detail}
        assert await _stored_executions(proposal_id) == []
        events = await _stored_execution_events(proposal_id)
        assert len(events) == 1
        assert events[0].event_type == "execution_blocked"
        assert events[0].error_message == expected_detail
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_rejects_missing_evidence_refs_before_live_write(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    async def fail_create_issue(**_kwargs):
        raise AssertionError("GitHub client should not be called")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal_id = await _seed_proposal(created["workspace"]["id"])
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal_id,
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "evidence_refs are required for live execution"
        }
        assert await _stored_executions(proposal_id) == []
        events = await _stored_execution_events(proposal_id)
        assert len(events) == 1
        assert events[0].event_type == "execution_blocked"
        assert events[0].error_code == "evidence_refs_are_required_for_live_execution"
    finally:
        await _cleanup_issue_action_fixture(marker)


@pytest.mark.parametrize(
    ("proposal_kwargs", "expected_status", "expected_detail"),
    [
        (
            {"status": ACTION_PROPOSAL_STATUS_PROPOSED},
            409,
            "action proposal is not approved",
        ),
        (
            {"target_provider": ACTION_TARGET_PROVIDER_INTERNAL},
            400,
            "unsupported action proposal",
        ),
        (
            {"action_type": ACTION_TYPE_INTERNAL_TODO},
            400,
            "unsupported action proposal",
        ),
    ],
)
async def test_execute_rejects_invalid_proposal_state_or_action(
    monkeypatch,
    proposal_kwargs: dict,
    expected_status: int,
    expected_detail: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal_id = await _seed_proposal(created["workspace"]["id"], **proposal_kwargs)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal_id,
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
        assert await _stored_executions(proposal_id) == []
        events = await _stored_execution_events(proposal_id)
        assert len(events) == 1
        assert events[0].event_type == "execution_blocked"
        assert events[0].error_message == expected_detail
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_execute_rejects_connection_from_another_workspace(monkeypatch) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)
    await _cleanup_issue_action_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        other_connection_id = await _create_connection(other["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=other_connection_id,
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "github connection not found"}
    finally:
        await _cleanup_issue_action_fixture(marker)
        await _cleanup_issue_action_fixture(other_marker)


@pytest.mark.parametrize(
    ("connection_kwargs", "expected_status", "expected_detail"),
    [
        (
            {"provider": INTEGRATION_PROVIDER_JIRA},
            400,
            "connection is not a GitHub connection",
        ),
        (
            {"status": INTEGRATION_CONNECTION_STATUS_REVOKED},
            409,
            "github connection is not connected",
        ),
        (
            {"status": INTEGRATION_CONNECTION_STATUS_DISABLED},
            409,
            "github connection is not connected",
        ),
        (
            {"status": INTEGRATION_CONNECTION_STATUS_ERROR},
            409,
            "github connection is not connected",
        ),
        (
            {"encrypted_access_token": None},
            409,
            "github connection has no encrypted access token",
        ),
    ],
)
async def test_execute_rejects_invalid_connection(
    monkeypatch,
    connection_kwargs: dict,
    expected_status: int,
    expected_detail: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(
            created["workspace"]["id"],
            **connection_kwargs,
        )

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_provider_failure_records_uncertain_outcome_without_token_leak(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    async def fail_create_issue(**_kwargs):
        raise GitHubIssueClientError(
            f"provider rejected access_token {PLAIN_EXECUTION_TOKEN}"
        )

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        response = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert response.status_code == 502
        assert response.json() == {
            "detail": "github issue outcome is uncertain; reconcile before retrying"
        }
        assert PLAIN_EXECUTION_TOKEN not in response.text
        stored_proposal = await _stored_proposal(proposal["id"])
        executions = await _stored_executions(proposal["id"])
        assert stored_proposal.status == ACTION_PROPOSAL_STATUS_APPROVED
        assert len(executions) == 1
        assert executions[0].status == ACTION_EXECUTION_STATUS_UNCERTAIN
        assert executions[0].error_message == (
            "github issue outcome is uncertain; reconcile before retrying"
        )
        assert PLAIN_EXECUTION_TOKEN not in str(executions[0].provider_response)
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_outcome_uncertain",
        ]
        assert events[-1].error_code == "provider_outcome_uncertain"
        assert events[-1].error_message == (
            "github issue outcome is uncertain; reconcile before retrying"
        )
        assert PLAIN_EXECUTION_TOKEN not in str(events[-1].event_metadata)
        audit = await _get_audit(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()["receipt"]["status"] == ACTION_EXECUTION_STATUS_UNCERTAIN
        assert audit.json()["receipt"]["provider_result"] == "uncertain"
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_pre_provider_token_failure_is_retryable_with_a_new_key(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    calls: list[dict] = []
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        broken_connection_id = await _create_connection(
            workspace_id,
            encrypted_access_token="not-an-encrypted-token",
        )

        failed = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=broken_connection_id,
            idempotency_key="broken-token-attempt",
        )

        assert failed.status_code == 502
        assert failed.json() == {"detail": "github token could not be decrypted"}
        stored_proposal = await _stored_proposal(proposal["id"])
        failed_executions = await _stored_executions(proposal["id"])
        assert stored_proposal.status == ACTION_PROPOSAL_STATUS_APPROVED
        assert len(failed_executions) == 1
        assert failed_executions[0].status == ACTION_EXECUTION_STATUS_FAILED

        _mock_successful_github_issue(monkeypatch, calls)
        valid_connection_id = await _create_connection(workspace_id)
        retried = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=valid_connection_id,
            idempotency_key="valid-token-retry",
        )

        assert retried.status_code == 200, retried.text
        assert len(calls) == 1
        executions = await _stored_executions(proposal["id"])
        assert [execution.status for execution in executions] == [
            ACTION_EXECUTION_STATUS_FAILED,
            ACTION_EXECUTION_STATUS_SUCCEEDED,
        ]
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_concurrent_execute_requests_make_one_provider_write(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)
    provider_entered = asyncio.Event()
    release_provider = asyncio.Event()
    calls: list[dict] = []

    async def delayed_create_issue(**kwargs):
        calls.append(kwargs)
        provider_entered.set()
        await release_provider.wait()
        return _github_issue_response(kwargs)

    monkeypatch.setattr(
        github_issue_execution_service,
        "create_issue",
        delayed_create_issue,
    )

    first_task: asyncio.Task | None = None
    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        first_task = asyncio.create_task(
            _execute_proposal(
                workspace_id,
                proposal["id"],
                owner_email,
                connection_id=connection_id,
                idempotency_key="concurrent-first",
            )
        )
        await asyncio.wait_for(provider_entered.wait(), timeout=2)
        second = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="concurrent-second",
        )

        assert second.status_code == 409
        assert second.json() == {
            "detail": "an execution claim already exists; reconcile it before retrying"
        }
        release_provider.set()
        first = await asyncio.wait_for(first_task, timeout=2)

        assert first.status_code == 200, first.text
        assert len(calls) == 1
        executions = await _stored_executions(proposal["id"])
        assert len(executions) == 1
        assert executions[0].status == ACTION_EXECUTION_STATUS_SUCCEEDED
    finally:
        release_provider.set()
        if first_task is not None and not first_task.done():
            first_task.cancel()
            await asyncio.gather(first_task, return_exceptions=True)
        await _cleanup_issue_action_fixture(marker)


async def test_idempotency_key_cannot_be_reused_for_another_proposal(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        first_proposal = await _create_approved_proposal(workspace_id, owner_email)
        second_proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        first = await _execute_proposal(
            workspace_id,
            first_proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="workspace-key-once",
        )
        second = await _execute_proposal(
            workspace_id,
            second_proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="workspace-key-once",
        )

        assert first.status_code == 200, first.text
        assert second.status_code == 409
        assert second.json() == {
            "detail": "idempotency key was already used with different execution input"
        }
        assert len(calls) == 1
        assert await _stored_executions(second_proposal["id"]) == []
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_uncertain_execution_reconciles_by_exact_provider_marker(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    calls: list[dict] = []
    list_calls: list[dict] = []
    await _cleanup_issue_action_fixture(marker)

    async def ambiguous_create_issue(**kwargs):
        calls.append(kwargs)
        raise GitHubIssueClientError("provider connection closed after request")

    async def list_created_issue(**kwargs):
        list_calls.append(kwargs)
        return [_github_issue_response(calls[0])]

    monkeypatch.setattr(
        github_issue_execution_service,
        "create_issue",
        ambiguous_create_issue,
    )
    monkeypatch.setattr(
        github_execution_result_sync_service,
        "list_issues",
        list_created_issue,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        actor_user_id = await _stored_user_id(owner_email)
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        executed = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="uncertain-found",
        )
        assert executed.status_code == 502

        synced = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert synced.status_code == 200, synced.text
        assert synced.json()["status"] == "synced"
        assert synced.json()["synced"] is True
        assert len(calls) == 1
        assert len(list_calls) == 1
        assert list_calls[0]["state"] == "all"
        assert list_calls[0]["repository_full_name"] == "qtwin-io/founderos-api"
        stored_proposal = await _stored_proposal(proposal["id"])
        executions = await _stored_executions(proposal["id"])
        assert stored_proposal.status == ACTION_PROPOSAL_STATUS_EXECUTED
        assert len(executions) == 1
        assert executions[0].status == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert executions[0].reconciled_at is not None
        assert executions[0].provider_response["number"] == 42
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_outcome_uncertain",
            "execution_result_sync_started",
            "execution_outcome_reconciled",
            "execution_result_synced",
        ]
        assert all(event.actor == f"user:{actor_user_id}" for event in events)
        audit = await _get_audit(workspace_id, proposal["id"], owner_email)
        assert audit.status_code == 200, audit.text
        assert audit.json()["receipt"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert audit.json()["receipt"]["provider_result"] == "succeeded"
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_absent_marker_allows_retry_only_with_new_idempotency_key(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    calls: list[dict] = []
    await _cleanup_issue_action_fixture(marker)

    async def create_issue_after_ambiguous_first_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise GitHubIssueClientError("provider connection closed after request")
        return _github_issue_response(kwargs, number=43)

    async def list_no_matching_issue(**_kwargs):
        return []

    monkeypatch.setattr(
        github_issue_execution_service,
        "create_issue",
        create_issue_after_ambiguous_first_call,
    )
    monkeypatch.setattr(
        github_execution_result_sync_service,
        "list_issues",
        list_no_matching_issue,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(workspace_id, owner_email)
        connection_id = await _create_connection(workspace_id)

        first = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="uncertain-absent",
        )
        assert first.status_code == 502

        pending = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == "reconciliation_pending"
        assert pending.json()["synced"] is False
        assert pending.json()["retry_after"] is not None
        pending_executions = await _stored_executions(proposal["id"])
        assert pending_executions[0].status == ACTION_EXECUTION_STATUS_UNCERTAIN
        assert pending_executions[0].reconciled_at is None

        early_retry = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="uncertain-too-early",
        )
        assert early_retry.status_code == 409
        assert early_retry.json() == {
            "detail": "an execution claim already exists; reconcile it before retrying"
        }
        assert len(calls) == 1

        await _age_execution_provider_start(
            proposal["id"],
            age=timedelta(minutes=2),
        )
        reconciled = await _sync_execution_result(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()["status"] == "write_not_observed"
        assert reconciled.json()["synced"] is False
        assert reconciled.json()["sync_job"] is None
        assert reconciled.json()["issue"]["number"] is None
        absent_audit = await _get_audit(workspace_id, proposal["id"], owner_email)
        assert absent_audit.status_code == 200, absent_audit.text
        assert absent_audit.json()["receipt"]["status"] == ACTION_EXECUTION_STATUS_FAILED
        assert absent_audit.json()["receipt"]["error_code"] == (
            "provider_write_not_observed"
        )

        same_key = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="uncertain-absent",
        )
        assert same_key.status_code == 409
        assert same_key.json() == {
            "detail": (
                "the idempotency key already completed without success; use a new key"
            )
        }

        retried = await _execute_proposal(
            workspace_id,
            proposal["id"],
            owner_email,
            connection_id=connection_id,
            idempotency_key="uncertain-retry-new",
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["execution"]["provider_response"]["number"] == 43
        assert len(calls) == 2
        executions = await _stored_executions(proposal["id"])
        assert [execution.status for execution in executions] == [
            ACTION_EXECUTION_STATUS_FAILED,
            ACTION_EXECUTION_STATUS_SUCCEEDED,
        ]
        assert executions[0].reconciled_at is not None
        assert executions[1].reconciled_at is None
        events = await _stored_execution_events(proposal["id"])
        event_types = [event.event_type for event in events]
        assert "execution_reconciliation_pending" in event_types
        assert "execution_write_not_observed" in event_types
        audit = await _get_audit(workspace_id, proposal["id"], owner_email)
        assert audit.status_code == 200, audit.text
        assert audit.json()["receipt"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert audit.json()["receipt"]["provider_result"] == "succeeded"
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_already_executed_proposal_cannot_execute_again(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    calls: list[dict] = []
    _mock_successful_github_issue(monkeypatch, calls)
    await _cleanup_issue_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _create_approved_proposal(created["workspace"]["id"], owner_email)
        connection_id = await _create_connection(created["workspace"]["id"])

        first = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )
        second = await _execute_proposal(
            created["workspace"]["id"],
            proposal["id"],
            owner_email,
            connection_id=connection_id,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        body = second.json()
        assert body["proposal"]["status"] == ACTION_PROPOSAL_STATUS_EXECUTED
        assert body["execution"]["status"] == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert body["receipt"]["provider_result"] == "succeeded"
        assert body["warnings"] == [
            "existing successful execution receipt returned; no external write occurred"
        ]
        assert len(calls) == 1
        events = await _stored_execution_events(proposal["id"])
        assert [event.event_type for event in events] == [
            "execution_confirmation_received",
            "execution_claimed",
            "execution_started",
            "execution_succeeded",
            "execution_duplicate_returned_existing_receipt",
        ]
    finally:
        await _cleanup_issue_action_fixture(marker)


async def test_approve_endpoint_still_does_not_execute(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_issue_action_fixture(marker)

    async def fail_create_issue(**_kwargs):
        raise AssertionError("approve endpoint should not call GitHub")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _post_proposal(created["workspace"]["id"], owner_email)
        executions_before = await _count(ActionExecution)

        approved = await _approve_proposal(
            created["workspace"]["id"],
            proposal,
            owner_email,
        )

        assert approved["status"] == ACTION_PROPOSAL_STATUS_APPROVED
        assert await _count(ActionExecution) == executions_before
    finally:
        await _cleanup_issue_action_fixture(marker)


def test_github_issue_execution_does_not_create_migration_file() -> None:
    migration_files = {
        path.name
        for path in (Path(__file__).resolve().parents[1] / "migrations" / "versions").glob(
            "*github_issue*"
        )
    }

    assert migration_files == set()
