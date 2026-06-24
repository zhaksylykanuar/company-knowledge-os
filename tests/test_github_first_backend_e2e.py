from __future__ import annotations

import builtins
from pathlib import Path
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.api.github as github_api
import app.connectors.github as github_connector
import app.services.founder_briefing_service as founder_briefing_service
import app.services.github_issue_execution_service as github_issue_execution_service
import app.services.github_normalization_service as github_normalization_service
import app.services.github_repository_read_service as github_repository_read_service
import app.services.source_control as source_control_service
from app.api.auth import settings
from app.db.action_models import (
    ACTION_EXECUTION_STATUS_SUCCEEDED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ActionExecution,
    ActionProposal,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import Membership, User, Workspace
from app.db.integration_models import IntegrationConnection, SyncJob
from app.main import app
from app.services.github_repository_read_service import GitHubRepositoryListResult

PLAIN_E2E_TOKEN = "plain-test-token-value"
FAKE_REPOSITORY_FULL_NAME = "octo/example"


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "secret_encryption_key", SecretStr("test-encryption-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str) -> dict[str, str]:
    return {
        "owner_email": f"github-e2e-{marker}@example.test",
        "owner_name": "GitHub E2E Owner",
        "workspace_name": f"GitHub E2E {marker}",
        "workspace_slug": f"github-e2e-{marker}",
    }


async def _cleanup_e2e_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-e2e-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-e2e-{marker}%@example.test")
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
                delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids))
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


async def _count(model: type, *, where=None) -> int:
    async with AsyncSessionLocal() as session:
        statement = select(func.count()).select_from(model)
        if where is not None:
            statement = statement.where(where)
        return int(await session.scalar(statement) or 0)


async def _stored_sync_job(sync_job_id: str) -> SyncJob:
    async with AsyncSessionLocal() as session:
        sync_job = await session.scalar(
            select(SyncJob).where(SyncJob.id == UUID(sync_job_id))
        )
        assert sync_job is not None
        return sync_job


async def _stored_proposal(proposal_id: str) -> ActionProposal:
    async with AsyncSessionLocal() as session:
        proposal = await session.scalar(
            select(ActionProposal).where(ActionProposal.id == UUID(proposal_id))
        )
        assert proposal is not None
        return proposal


async def _stored_executions(proposal_id: str) -> list[ActionExecution]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(ActionExecution).where(
                    ActionExecution.action_proposal_id == UUID(proposal_id)
                )
            )
        ).scalars()
        return list(rows)


def _fake_repository() -> dict:
    return {
        "id": FAKE_REPOSITORY_FULL_NAME,
        "name": "example",
        "full_name": FAKE_REPOSITORY_FULL_NAME,
        "default_branch": "main",
        "visibility": "private",
        "archived": False,
        "source_url": "https://github.com/octo/example",
        "last_activity_at": "2026-06-20T00:00:00+00:00",
        "source": "repository_inventory",
        "evidence_refs": [
            {
                "kind": "repository_inventory_snapshot",
                "source": "backend_e2e_test",
                "ref": FAKE_REPOSITORY_FULL_NAME,
                "url": None,
            }
        ],
        "metadata": {
            "source_class": "backend_e2e_test",
            "provider_key": "github",
            "repo_not_jira_project": True,
        },
    }


def _install_repository_read_fake(monkeypatch, calls: list[dict]) -> None:
    async def fake_repository_read(**kwargs):
        calls.append(kwargs)
        return GitHubRepositoryListResult(
            repositories=[_fake_repository()],
            count=1,
            source="repository_inventory",
            is_live=False,
            warnings=["repository inventory served from backend e2e fake"],
        )

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )
    monkeypatch.setattr(github_api, "list_workspace_github_repositories", fake_repository_read)
    monkeypatch.setattr(
        github_normalization_service.github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )
    monkeypatch.setattr(
        founder_briefing_service.github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )


def _install_no_live_call_guards(monkeypatch, issue_calls: list[dict]) -> None:
    async def fake_create_issue(**kwargs):
        issue_calls.append(kwargs)
        assert kwargs["access_token"] == PLAIN_E2E_TOKEN
        return {
            "id": 123,
            "number": 1,
            "html_url": "https://example.test/octo/example/issues/1",
            "title": "Backend E2E smoke issue",
            "token": PLAIN_E2E_TOKEN,
        }

    async def fail_source_action(*_args, **_kwargs):
        raise AssertionError("source_control should not run in backend e2e smoke")

    def fail_live_connector(*_args, **_kwargs):
        raise AssertionError("live provider connector should not run in backend e2e smoke")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fake_create_issue)
    monkeypatch.setattr(source_control_service, "request_source_action", fail_source_action)
    monkeypatch.setattr(github_connector, "list_repository_events", fail_live_connector)
    monkeypatch.setattr(github_connector, "fetch_issue_events", fail_live_connector)
    monkeypatch.setattr(github_connector, "fetch_pull_request_events", fail_live_connector)
    monkeypatch.setattr(
        github_connector,
        "fetch_org_repository_inventory_summary",
        fail_live_connector,
    )

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise AssertionError("OpenAI should not be imported in backend e2e smoke")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


async def test_github_first_backend_e2e_smoke_flow(monkeypatch) -> None:
    marker = uuid4().hex
    owner_email = _bootstrap_payload(marker)["owner_email"]
    _set_auth(monkeypatch)
    repository_calls: list[dict] = []
    issue_calls: list[dict] = []
    _install_repository_read_fake(monkeypatch, repository_calls)
    _install_no_live_call_guards(monkeypatch, issue_calls)
    await _cleanup_e2e_fixture(marker)
    response_texts: list[str] = []

    try:
        async with _async_client() as client:
            bootstrap = await client.post(
                "/api/v1/workspaces/bootstrap",
                headers=_headers(),
                json=_bootstrap_payload(marker),
            )
            response_texts.append(bootstrap.text)
            assert bootstrap.status_code == 201, bootstrap.text
            bootstrap_body = bootstrap.json()
            workspace_id = bootstrap_body["workspace"]["id"]
            user_id = bootstrap_body["user"]["id"]
            assert bootstrap_body["user"]["email"] == owner_email
            assert bootstrap_body["membership"]["role"] == "owner"

            initial_status = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/connection-status",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            response_texts.append(initial_status.text)
            assert initial_status.status_code == 200
            assert initial_status.json()["status"] == "local_bridge_only"
            assert initial_status.json()["has_connection_record"] is False
            assert initial_status.json()["is_live"] is False

            connection_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "display_name": "E2E GitHub connection",
                    "external_account_id": "e2e-org",
                    "access_token": PLAIN_E2E_TOKEN,
                    "scopes": ["repo"],
                    "metadata": {"purpose": "backend-e2e-smoke"},
                },
            )
            response_texts.append(connection_response.text)
            assert connection_response.status_code == 200, connection_response.text
            connection_body = connection_response.json()
            connection = connection_body["connection"]
            connection_id = connection["id"]
            assert connection_body["is_live"] is False
            assert connection["status"] == "connected"
            assert connection["has_access_token"] is True
            assert PLAIN_E2E_TOKEN not in connection_response.text
            assert "fernet:v1:" not in connection_response.text

            connected_status = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/connection-status",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            response_texts.append(connected_status.text)
            assert connected_status.status_code == 200
            status_body = connected_status.json()
            assert status_body["status"] == "connected"
            assert status_body["has_connection_record"] is True
            assert status_body["has_valid_token_record"] is True
            assert status_body["is_live"] is False
            assert "token" not in status_body
            assert PLAIN_E2E_TOKEN not in connected_status.text

            repositories_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/repositories",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            response_texts.append(repositories_response.text)
            assert repositories_response.status_code == 200
            repositories_body = repositories_response.json()
            assert repositories_body["is_live"] is False
            assert repositories_body["count"] == 1
            assert (
                repositories_body["repositories"][0]["full_name"]
                == FAKE_REPOSITORY_FULL_NAME
            )
            assert repositories_body["repositories"][0]["evidence_refs"][0]["ref"] == (
                FAKE_REPOSITORY_FULL_NAME
            )

            sync_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "sync_type": "manual",
                    "cursor_before": None,
                    "notes": "backend e2e smoke",
                },
            )
            response_texts.append(sync_response.text)
            assert sync_response.status_code == 201, sync_response.text
            sync_body = sync_response.json()
            sync_job = sync_body["sync_job"]
            sync_job_id = sync_job["id"]
            assert sync_body["is_live"] is False
            assert sync_body["execution_started"] is False
            assert sync_job["provider"] == "github"
            assert sync_job["status"] == "queued"
            assert sync_job["sync_type"] == "manual"

            normalize_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "include_repositories": True,
                    "include_issues": True,
                    "include_pull_requests": True,
                    "persist_if_supported": False,
                },
            )
            response_texts.append(normalize_response.text)
            assert normalize_response.status_code == 200, normalize_response.text
            normalize_body = normalize_response.json()
            assert normalize_body["is_live"] is False
            assert normalize_body["provider_sync_started"] is False
            assert normalize_body["local_normalization_performed"] is True
            assert normalize_body["persistence_mode"] == "projection"
            assert normalize_body["counts"]["repositories"] == 1
            assert normalize_body["sync_job"]["status"] in {"succeeded", "partial"}
            assert normalize_body["normalized"]["repositories"][0]["full_name"] == (
                FAKE_REPOSITORY_FULL_NAME
            )
            assert normalize_body["normalized"]["issues"] == []
            assert normalize_body["normalized"]["pull_requests"] == []

            sync_job_count_before_briefing = await _count(SyncJob)
            sync_job_before_briefing = await _stored_sync_job(sync_job_id)

            briefing_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/briefings/manual",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "focus": ["github", "sync", "repositories"],
                    "include_github": True,
                    "include_connections": True,
                    "include_sync_jobs": True,
                    "include_repository_inventory": True,
                    "limit": 20,
                },
            )
            response_texts.append(briefing_response.text)
            assert briefing_response.status_code == 200, briefing_response.text
            briefing = briefing_response.json()["briefing"]
            assert briefing["is_live"] is False
            assert briefing["llm_used"] is False
            assert briefing["persistence"] == "transient"
            assert briefing["signals"]["github"]["connection_status"] == "connected"
            assert briefing["signals"]["github"]["repository_count"] == 1
            assert briefing["signals"]["github"]["latest_sync_job_status"] in {
                "succeeded",
                "partial",
            }
            assert any(item["evidence_refs"] for item in briefing["items"])
            assert await _count(SyncJob) == sync_job_count_before_briefing
            sync_job_after_briefing = await _stored_sync_job(sync_job_id)
            assert sync_job_after_briefing.status == sync_job_before_briefing.status
            assert sync_job_after_briefing.logs == sync_job_before_briefing.logs

            action_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "target_provider": "github",
                    "action_type": "create_github_issue",
                    "title": "Create backend E2E smoke issue",
                    "description": "Proposal created by backend E2E smoke test.",
                    "payload": {
                        "repository_full_name": FAKE_REPOSITORY_FULL_NAME,
                        "title": "Backend E2E smoke issue",
                        "body": "This is generated by a mocked backend smoke test.",
                    },
                    "evidence_refs": [
                        {
                            "kind": "repository",
                            "source": "backend_e2e_test",
                            "ref": FAKE_REPOSITORY_FULL_NAME,
                            "url": None,
                        }
                    ],
                    "created_by": "user",
                },
            )
            response_texts.append(action_response.text)
            assert action_response.status_code == 201, action_response.text
            proposal = action_response.json()["proposal"]
            proposal_id = proposal["id"]
            assert proposal["status"] == "proposed"
            assert proposal["execution_started"] is False
            assert proposal["evidence_refs"][0]["ref"] == FAKE_REPOSITORY_FULL_NAME
            assert await _stored_executions(proposal_id) == []

            approve_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            response_texts.append(approve_response.text)
            assert approve_response.status_code == 200, approve_response.text
            approve_body = approve_response.json()
            assert approve_body["proposal"]["status"] == "approved"
            assert approve_body["execution_started"] is False
            assert await _stored_executions(proposal_id) == []

            sync_job_count_before_execute = await _count(SyncJob)
            execute_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execute",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "connection_id": connection_id,
                    "confirm_external_write": True,
                    "idempotency_key": "backend-e2e-smoke",
                },
            )
            response_texts.append(execute_response.text)
            assert execute_response.status_code == 200, execute_response.text
            execute_body = execute_response.json()
            assert execute_body["proposal"]["status"] == "executed"
            assert execute_body["execution"]["status"] == "succeeded"
            assert execute_body["execution"]["external_id"].endswith("/issues/1")
            assert execute_body["execution"]["provider_response"]["number"] == 1
            assert "token" not in execute_body["execution"]["provider_response"]
            assert execute_body["is_live"] is True
            assert execute_body["external_write_performed"] is True
            assert execute_body["provider"] == "github"
            assert await _count(SyncJob) == sync_job_count_before_execute

        stored_proposal = await _stored_proposal(proposal_id)
        executions = await _stored_executions(proposal_id)
        assert stored_proposal.status == ACTION_PROPOSAL_STATUS_EXECUTED
        assert len(executions) == 1
        assert executions[0].status == ACTION_EXECUTION_STATUS_SUCCEEDED
        assert executions[0].external_id.endswith("/issues/1")
        assert executions[0].provider_response["html_url"].endswith("/issues/1")
        assert executions[0].provider_response["title"] == "Backend E2E smoke issue"
        assert PLAIN_E2E_TOKEN not in str(executions[0].provider_response)
        assert PLAIN_E2E_TOKEN not in "".join(response_texts)
        assert "fernet:v1:" not in "".join(response_texts)
        assert len(issue_calls) == 1
        assert issue_calls[0]["repository_full_name"] == FAKE_REPOSITORY_FULL_NAME
        assert issue_calls[0]["title"] == "Backend E2E smoke issue"
        assert issue_calls[0]["access_token"] == PLAIN_E2E_TOKEN
        assert repository_calls
        assert Path("migrations/versions").exists()
        assert not list(Path("migrations/versions").glob("*e2e*"))
        assert user_id

    finally:
        await _cleanup_e2e_fixture(marker)
