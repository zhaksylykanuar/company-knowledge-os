from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_issue_execution_service as github_issue_execution_service
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.action_models import (
    ACTION_CREATED_BY_USER,
    ACTION_EXECUTION_STATUS_FAILED,
    ACTION_EXECUTION_STATUS_SUCCEEDED,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_PROPOSAL_STATUS_FAILED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ACTION_TYPE_INTERNAL_TODO,
    ActionExecution,
    ActionProposal,
)
from app.db.base import AsyncSessionLocal
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
    monkeypatch.setattr(settings, "enable_write_actions", True)


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _block_live_github_issue_client(monkeypatch):
    async def fail_create_issue(**_kwargs):
        raise AssertionError("GitHub issue client must be mocked in tests")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)


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
                    delete(ActionExecution).where(
                        ActionExecution.action_proposal_id.in_(proposal_ids)
                    )
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
    return response.json()


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
    proposal_id: str,
    owner_email: str,
) -> dict:
    async with _async_client() as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/approve",
            headers=_headers(),
            params={"owner_email": owner_email},
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
    return await _approve_proposal(workspace_id, proposal["id"], owner_email)


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
        "idempotency_key": idempotency_key,
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
                select(ActionExecution).where(
                    ActionExecution.action_proposal_id == UUID(str(proposal_id))
                )
            )
        ).scalars()
        return list(rows)


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _mock_successful_github_issue(monkeypatch, calls: list[dict]) -> None:
    async def fake_create_issue(**kwargs):
        calls.append(kwargs)
        assert kwargs["access_token"] == PLAIN_EXECUTION_TOKEN
        return {
            "id": 987654,
            "number": 42,
            "html_url": "https://github.com/qtwin-io/founderos-api/issues/42",
            "url": "https://api.github.com/repos/qtwin-io/founderos-api/issues/42",
            "state": "open",
            "title": kwargs["title"],
            "body": kwargs.get("body"),
            "token": PLAIN_EXECUTION_TOKEN,
        }

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fake_create_issue)


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
        assert body["audit"][0]["event"] == "proposal_created"
        assert body["audit"][1]["event"] == "proposal_approved"
        assert body["warnings"] == [
            "Execution preview is dry-run only and does not call GitHub."
        ]
        assert await _stored_executions(proposal["id"]) == []
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
        assert await _stored_executions(proposal_id) == []
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
        assert body["execution"]["external_id"].endswith("/issues/42")
        assert body["execution"]["provider_response"]["number"] == 42
        assert "body" not in body["execution"]["provider_response"]
        assert "token" not in body["execution"]["provider_response"]
        assert PLAIN_EXECUTION_TOKEN not in response.text
        assert body["is_live"] is True
        assert body["external_write_performed"] is True
        assert body["provider"] == INTEGRATION_PROVIDER_GITHUB
        assert calls[0]["repository_full_name"] == "qtwin-io/founderos-api"
        assert await _count(ActionExecution) >= 1
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


async def test_provider_failure_creates_failed_execution_without_token_leak(
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
        assert response.json() == {"detail": "github issue creation failed"}
        assert PLAIN_EXECUTION_TOKEN not in response.text
        stored_proposal = await _stored_proposal(proposal["id"])
        executions = await _stored_executions(proposal["id"])
        assert stored_proposal.status == ACTION_PROPOSAL_STATUS_FAILED
        assert len(executions) == 1
        assert executions[0].status == ACTION_EXECUTION_STATUS_FAILED
        assert executions[0].error_message == "github issue creation failed"
        assert PLAIN_EXECUTION_TOKEN not in str(executions[0].provider_response)
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
        assert second.status_code == 409
        assert second.json() == {"detail": "action proposal already executed"}
        assert len(calls) == 1
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
            proposal["id"],
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
