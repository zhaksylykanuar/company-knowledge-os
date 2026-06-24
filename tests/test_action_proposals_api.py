from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.action_models import (
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_PROPOSAL_STATUS_REJECTED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ACTION_TYPE_INTERNAL_TODO,
    ActionExecution,
    ActionExecutionEvent,
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
from app.main import app


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str, *, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"action-{marker}{suffix}@example.test",
        "owner_name": "Action Owner",
        "workspace_name": f"Action {marker}{suffix}",
        "workspace_slug": f"action-{marker}{suffix}",
    }


def _proposal_payload(**overrides) -> dict:
    payload = {
        "target_provider": ACTION_TARGET_PROVIDER_GITHUB,
        "action_type": ACTION_TYPE_CREATE_GITHUB_ISSUE,
        "title": "Create follow-up issue",
        "description": "Track the action after founder review.",
        "payload": {
            "repository_full_name": "qtwin-io/founderos-api",
            "title": "Follow up on founderOS signal",
            "body": "Local-only proposal body.",
        },
        "evidence_refs": [
            {
                "kind": "repository",
                "source": "github_repository_read_api",
                "ref": "qtwin-io/founderos-api",
                "url": None,
            }
        ],
        "created_by": "user",
    }
    payload.update(overrides)
    return payload


async def _cleanup_action_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"action-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"action-{marker}%@example.test"))
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
                delete(ActionProposal).where(
                    ActionProposal.workspace_id.in_(workspace_ids)
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
    email = f"action-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"Action {role}")
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


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def test_action_models_register_with_metadata() -> None:
    assert ActionProposal.__tablename__ == "action_proposals"
    assert ActionExecution.__tablename__ == "action_executions"
    assert ActionExecutionEvent.__tablename__ == "action_execution_events"
    assert "action_proposals" in ActionProposal.metadata.tables
    assert "action_executions" in ActionExecution.metadata.tables
    assert "action_execution_events" in ActionExecutionEvent.metadata.tables


async def test_action_migration_tables_exist() -> None:
    async with AsyncSessionLocal() as session:
        action_proposals = await session.scalar(
            text("select to_regclass('public.action_proposals')")
        )
        action_executions = await session.scalar(
            text("select to_regclass('public.action_executions')")
        )
        action_execution_events = await session.scalar(
            text("select to_regclass('public.action_execution_events')")
        )

    assert action_proposals == "action_proposals"
    assert action_executions == "action_executions"
    assert action_execution_events == "action_execution_events"


async def test_create_proposal_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=_proposal_payload(),
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    finally:
        await _cleanup_action_fixture(marker)


async def test_create_proposal_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                headers=_headers(),
                json=_proposal_payload(),
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_action_fixture(marker)


@pytest.mark.parametrize(
    "role",
    [MEMBERSHIP_ROLE_OWNER, MEMBERSHIP_ROLE_ADMIN, MEMBERSHIP_ROLE_MEMBER],
)
async def test_owner_admin_member_can_create_proposal(monkeypatch, role: str) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        user_email = _bootstrap_payload(marker)["owner_email"]
        if role != MEMBERSHIP_ROLE_OWNER:
            user_email = await _add_workspace_user(
                created["workspace"]["id"],
                marker,
                role=role,
                suffix=role,
            )

        proposal = await _post_proposal(created["workspace"]["id"], user_email)

        assert proposal["status"] == ACTION_PROPOSAL_STATUS_PROPOSED
        assert proposal["target_provider"] == ACTION_TARGET_PROVIDER_GITHUB
        assert proposal["action_type"] == ACTION_TYPE_CREATE_GITHUB_ISSUE
        assert proposal["is_live"] is False
        assert proposal["execution_started"] is False
        assert proposal["created_by_user_id"] is not None
        assert proposal["evidence_refs"][0]["ref"] == "qtwin-io/founderos-api"
    finally:
        await _cleanup_action_fixture(marker)


async def test_viewer_cannot_create_proposal(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        viewer_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_VIEWER,
            suffix="viewer",
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                headers=_headers(),
                params={"owner_email": viewer_email},
                json=_proposal_payload(),
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_action_fixture(marker)


@pytest.mark.parametrize(
    ("payload", "expected_status", "expected_detail"),
    [
        (
            _proposal_payload(target_provider="jira"),
            400,
            "unknown target_provider",
        ),
        (
            _proposal_payload(action_type="archive_repository"),
            400,
            "unknown action_type",
        ),
        (
            _proposal_payload(
                target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                action_type=ACTION_TYPE_CREATE_GITHUB_ISSUE,
            ),
            400,
            "invalid provider/action pair",
        ),
        (_proposal_payload(title=" "), 422, None),
        (_proposal_payload(payload=["not", "object"]), 422, None),
        (
            _proposal_payload(payload={"nested": {"access_token": "placeholder"}}),
            400,
            "payload contains secret-like key: access_token",
        ),
    ],
)
async def test_create_proposal_rejects_invalid_payloads(
    monkeypatch,
    payload: dict,
    expected_status: int,
    expected_detail: str | None,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=payload,
            )

        assert response.status_code == expected_status
        if expected_detail is not None:
            assert response.json() == {"detail": expected_detail}
    finally:
        await _cleanup_action_fixture(marker)


async def test_list_filters_and_workspace_scoping(monkeypatch) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)
    await _cleanup_action_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        other_owner_email = _bootstrap_payload(other_marker)["owner_email"]

        github_proposal = await _post_proposal(created["workspace"]["id"], owner_email)
        await _post_proposal(
            created["workspace"]["id"],
            owner_email,
            payload=_proposal_payload(
                target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                action_type=ACTION_TYPE_INTERNAL_TODO,
                title="Internal follow-up",
                payload={"note": "Local follow-up"},
            ),
        )
        await _post_proposal(other["workspace"]["id"], other_owner_email)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                headers=_headers(),
                params={
                    "owner_email": owner_email,
                    "target_provider": ACTION_TARGET_PROVIDER_GITHUB,
                    "action_type": ACTION_TYPE_CREATE_GITHUB_ISSUE,
                    "status": ACTION_PROPOSAL_STATUS_PROPOSED,
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["is_live"] is False
        assert body["proposals"][0]["id"] == github_proposal["id"]
    finally:
        await _cleanup_action_fixture(marker)
        await _cleanup_action_fixture(other_marker)


async def test_detail_rejects_cross_workspace_access(monkeypatch) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)
    await _cleanup_action_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        other_owner_email = _bootstrap_payload(other_marker)["owner_email"]
        proposal = await _post_proposal(created["workspace"]["id"], owner_email)

        async with _async_client() as client:
            allowed = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            cross_workspace = await client.get(
                f"/api/v1/workspaces/{other['workspace']['id']}/actions/proposals/{proposal['id']}",
                headers=_headers(),
                params={"owner_email": other_owner_email},
            )

        assert allowed.status_code == 200
        assert allowed.json()["id"] == proposal["id"]
        assert cross_workspace.status_code == 404
        assert cross_workspace.json() == {"detail": "action proposal not found"}
    finally:
        await _cleanup_action_fixture(marker)
        await _cleanup_action_fixture(other_marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_OWNER, MEMBERSHIP_ROLE_ADMIN])
async def test_owner_admin_can_approve_without_execution(
    monkeypatch,
    role: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        actor_email = _bootstrap_payload(marker)["owner_email"]
        if role != MEMBERSHIP_ROLE_OWNER:
            actor_email = await _add_workspace_user(
                created["workspace"]["id"],
                marker,
                role=role,
                suffix=role,
            )
        proposal = await _post_proposal(
            created["workspace"]["id"],
            _bootstrap_payload(marker)["owner_email"],
        )
        executions_before = await _count(ActionExecution)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/approve",
                headers=_headers(),
                params={"owner_email": actor_email},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["proposal"]["status"] == ACTION_PROPOSAL_STATUS_APPROVED
        assert body["execution_started"] is False
        assert body["is_live"] is False
        assert any("deferred" in warning for warning in body["warnings"])
        assert await _count(ActionExecution) == executions_before
    finally:
        await _cleanup_action_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER])
async def test_member_viewer_cannot_approve(monkeypatch, role: str) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        actor_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=role,
            suffix=role,
        )
        proposal = await _post_proposal(
            created["workspace"]["id"],
            _bootstrap_payload(marker)["owner_email"],
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/approve",
                headers=_headers(),
                params={"owner_email": actor_email},
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_action_fixture(marker)


async def test_approve_reject_invalid_transitions_fail(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        approved = await _post_proposal(created["workspace"]["id"], owner_email)
        rejected = await _post_proposal(
            created["workspace"]["id"],
            owner_email,
            payload=_proposal_payload(title="Reject me"),
        )

        async with _async_client() as client:
            approve_once = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            approve_twice = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            reject_once = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{rejected['id']}/reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={"reason": "Not needed"},
            )
            reject_twice = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{rejected['id']}/reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={"reason": "Still not needed"},
            )
            reject_approved = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={"reason": "Too late"},
            )

        assert approve_once.status_code == 200
        assert approve_twice.status_code == 409
        assert approve_twice.json() == {
            "detail": "action proposal is not in proposed status"
        }
        assert reject_once.status_code == 200
        assert reject_once.json()["proposal"]["status"] == ACTION_PROPOSAL_STATUS_REJECTED
        assert reject_once.json()["proposal"]["rejection_reason"] == "Not needed"
        assert reject_twice.status_code == 409
        assert reject_approved.status_code == 409
    finally:
        await _cleanup_action_fixture(marker)


def test_action_api_does_not_create_extra_migration_files() -> None:
    migration_files = {
        path.name
        for path in (Path(__file__).resolve().parents[1] / "migrations" / "versions").glob(
            "*action_proposal*"
        )
    }

    assert migration_files == {"f5a6b7c8d9e0_add_action_proposal_foundation.py"}
