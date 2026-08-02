from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.action_models import (
    ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED,
    ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED,
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
from app.db.canonical_models import Repository, SourceRecord
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
import app.services.action_proposal_decision_service as action_proposal_decision_service
from app.services.action_proposal_service import (
    ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
    ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS,
    ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
    ActionProposalCreateInput,
    ActionProposalError,
    action_proposal_version,
    validate_action_proposal_input,
)
from app.services.action_proposal_decision_service import (
    ActionProposalDecisionCommand,
    ActionProposalDecisionConflictError,
    ActionProposalDecisionForbiddenError,
    decide_action_proposal,
)


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


def _decision_payload(
    proposal: dict,
    *,
    idempotency_key: str | None = None,
    reason: str | None = None,
    expected_snapshot_id: str | None = None,
) -> dict:
    payload = {
        "idempotency_key": idempotency_key or f"decision-{uuid4()}",
        "proposal_version": proposal["proposal_version"],
    }
    if reason is not None:
        payload["reason"] = reason
    if expected_snapshot_id is not None:
        payload["expected_snapshot_id"] = expected_snapshot_id
    return payload


def _bulk_decision_item(
    proposal: dict,
    *,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    return {
        "proposal_id": proposal["id"],
        "idempotency_key": idempotency_key or f"bulk-decision-{uuid4()}",
        "proposal_version": proposal["proposal_version"],
    }


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
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Repository).where(Repository.workspace_id.in_(workspace_ids))
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
                repo_metadata={"fixture": "action_proposals"},
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


async def test_atomic_action_execution_schema_is_enforced() -> None:
    async with AsyncSessionLocal() as session:
        columns = dict(
            (
                await session.execute(
                    text(
                        """
                        select column_name, is_nullable
                        from information_schema.columns
                        where table_schema = 'public'
                          and table_name = 'action_executions'
                        """
                    )
                )
            ).all()
        )
        indexes = set(
            (
                await session.execute(
                    text(
                        """
                        select indexname
                        from pg_indexes
                        where schemaname = 'public'
                          and tablename = 'action_executions'
                        """
                    )
                )
            ).scalars()
        )
        constraints = set(
            (
                await session.execute(
                    text(
                        """
                        select conname
                        from pg_constraint
                        where conrelid = 'public.action_executions'::regclass
                        """
                    )
                )
            ).scalars()
        )
        status_constraint = await session.scalar(
            text(
                """
                select pg_get_constraintdef(oid)
                from pg_constraint
                where conrelid = 'public.action_executions'::regclass
                  and conname = 'ck_action_executions_status'
                """
            )
        )

    assert {
        "workspace_id": "NO",
        "client_idempotency_key": "NO",
        "request_hash": "NO",
        "claimed_at": "NO",
        "requested_by_user_id": "YES",
        "connection_id": "YES",
        "reconciled_at": "YES",
    }.items() <= columns.items()
    assert {
        "uq_action_executions_workspace_client_idempotency_key",
        "uq_action_executions_one_active_or_success_per_proposal",
    } <= indexes
    assert {
        "fk_action_executions_workspace_id",
        "fk_action_executions_requested_by_user_id",
        "fk_action_executions_connection_id",
        "ck_action_executions_status",
    } <= constraints
    assert status_constraint is not None
    assert {"claimed", "running", "succeeded", "failed", "uncertain"} <= {
        status
        for status in ("claimed", "running", "succeeded", "failed", "uncertain")
        if status in status_constraint.casefold()
    }


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


async def test_public_proposal_origin_defaults_to_user_and_rejects_internal_origins(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        default_payload = _proposal_payload()
        default_payload.pop("created_by")

        proposal = await _post_proposal(
            created["workspace"]["id"],
            owner_email,
            payload=default_payload,
        )
        assert proposal["created_by"] == "user"
        assert proposal["created_by_user_id"] is not None

        async with _async_client() as client:
            for internal_origin in ("ai", "system"):
                response = await client.post(
                    f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                    headers=_headers(),
                    params={"owner_email": owner_email},
                    json=_proposal_payload(created_by=internal_origin),
                )
                assert response.status_code == 422
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


async def test_repo_audit_import_creates_local_internal_todos_with_evidence(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/import-repo-audit",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "findings": [
                        {
                            "repository_full_name": "qtwin-io/base-collector",
                            "title": "Проверить CI token=placeholder",
                            "summary": "CI не найден; password=placeholder",
                            "severity": "high",
                            "risks": ["ci_not_detected"],
                            "evidence_refs": [
                                "external-audit:base-collector:ci"
                            ],
                            "recommended_next_step": "Добавить CI",
                            "area_candidate": "OPS",
                        },
                        {
                            "repository_full_name": "bad repo",
                            "summary": "invalid repo identity",
                            "evidence_refs": ["external-audit:bad"],
                        },
                        {
                            "repository_full_name": "qtwin-io/no-evidence",
                            "summary": "missing evidence",
                            "evidence_refs": [" "],
                        },
                    ]
                },
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["succeeded_count"] == 1
        assert payload["failed_count"] == 2
        assert payload["is_live"] is False
        assert payload["execution_started"] is False
        proposal = payload["proposals"][0]
        assert proposal["target_provider"] == ACTION_TARGET_PROVIDER_INTERNAL
        assert proposal["action_type"] == ACTION_TYPE_INTERNAL_TODO
        assert proposal["payload"]["source"] == "repo_audit_import"
        assert proposal["payload"]["repository_full_name"] == "qtwin-io/base-collector"
        assert proposal["evidence_refs"] == [
            {
                "kind": "repository",
                "source": "github",
                "ref": "qtwin-io/base-collector",
                "url": None,
            }
        ]
        assert "external-audit:base-collector:ci" not in str(proposal)
        assert "token=[redacted]" in proposal["title"]
        assert "password=[redacted]" in proposal["description"]
        assert "placeholder" not in proposal["title"]
        assert "placeholder" not in proposal["description"]
        assert {
            failure["detail"] for failure in payload["failures"]
        } == {
            "repository_full_name must be in owner/repo format",
            "repo-audit import finding requires evidence_refs",
        }
    finally:
        await _cleanup_action_fixture(marker)


async def test_repo_audit_import_requires_member_role(monkeypatch) -> None:
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
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/import-repo-audit",
                headers=_headers(),
                params={"owner_email": viewer_email},
                json={
                    "findings": [
                        {
                            "repository_full_name": "qtwin-io/base-collector",
                            "summary": "CI не найден",
                            "evidence_refs": ["external-audit:base-collector:ci"],
                        }
                    ]
                },
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
        (
            _proposal_payload(
                evidence_refs=[
                    {
                        "kind": "repository",
                        "source": "github",
                        "ref": "qtwin-io/founderos-api",
                        "unexpected": "arbitrary-json",
                    }
                ]
            ),
            400,
            "evidence_refs items must match the evidence_ref.v1 schema",
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


@pytest.mark.parametrize(
    ("field_name", "oversized_value", "max_bytes"),
    (
        (
            "payload",
            {"note": "é" * (ACTION_PROPOSAL_PAYLOAD_MAX_BYTES // 2 + 1)},
            ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
        ),
        (
            "evidence_refs",
            [
                {
                    "kind": "repository",
                    "note": "é" * (ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES // 2 + 1),
                }
            ],
            ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
        ),
    ),
)
async def test_create_proposal_rejects_oversized_utf8_json(
    monkeypatch,
    field_name: str,
    oversized_value: object,
    max_bytes: int,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        payload = _proposal_payload()
        payload[field_name] = oversized_value
        assert len(json.dumps(oversized_value).encode("utf-8")) > max_bytes
        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=payload,
            )

        assert response.status_code == 400
        assert response.json() == {
            "detail": (f"{field_name} exceeds {max_bytes} UTF-8 serialized bytes")
        }
        async with AsyncSessionLocal() as session:
            persisted_count = await session.scalar(
                select(func.count(ActionProposal.id)).where(
                    ActionProposal.workspace_id == UUID(created["workspace"]["id"])
                )
            )
        assert persisted_count == 0
    finally:
        await _cleanup_action_fixture(marker)


def test_shared_action_validation_caps_evidence_ref_items() -> None:
    with pytest.raises(
        ActionProposalError,
        match=f"evidence_refs exceeds {ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS} items",
    ):
        validate_action_proposal_input(
            ActionProposalCreateInput(
                target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                action_type=ACTION_TYPE_INTERNAL_TODO,
                title="Bound internal evidence",
                payload={},
                evidence_refs=[{}] * (ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS + 1),
            )
        )


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
            decision_payload = _decision_payload(proposal)
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/approve",
                headers=_headers(),
                params={"owner_email": actor_email},
                json=decision_payload,
            )
            audit_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/audit",
                headers=_headers(),
                params={"owner_email": actor_email},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["proposal"]["status"] == ACTION_PROPOSAL_STATUS_APPROVED
        assert body["proposal"]["proposal_version"] != proposal["proposal_version"]
        assert body["execution_started"] is False
        assert body["is_live"] is False
        assert body["decision_receipt"] == {
            "receipt_id": body["decision_receipt"]["receipt_id"],
            "proposal_id": proposal["id"],
            "decision": "approved",
            "recorded_at": body["decision_receipt"]["recorded_at"],
            "replayed": False,
            "external_write_performed": False,
            "proposal_version": proposal["proposal_version"],
        }
        assert any("deferred" in warning for warning in body["warnings"])
        assert await _count(ActionExecution) == executions_before
        assert audit_response.status_code == 200, audit_response.text
        audit = audit_response.json()
        assert audit["events"][0]["event_type"] == ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED
        assert audit["events"][0]["status"] == "recorded"
        assert audit["events"][0]["provider"] == ACTION_TARGET_PROVIDER_GITHUB
        assert audit["events"][0]["action"] == ACTION_TYPE_CREATE_GITHUB_ISSUE
        assert audit["events"][0]["external_execution_enabled"] is False
        assert audit["events"][0]["confirmation_received"] is False
        assert audit["events"][0]["event_metadata"]["decision"] == "approved"
        assert audit["events"][0]["event_metadata"]["bulk"] is False
        assert audit["events"][0]["id"] == body["decision_receipt"]["receipt_id"]
        assert audit["receipt"]["external_write_performed"] is False
        assert audit["receipt"]["provider_result"] == "none"
    finally:
        await _cleanup_action_fixture(marker)


async def test_approval_rejects_fabricated_deleted_unrelated_and_foreign_evidence(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    foreign_marker = f"{marker}-foreign"
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)
    await _cleanup_action_fixture(foreign_marker)

    try:
        created = await _bootstrap_workspace(marker)
        foreign = await _bootstrap_workspace(foreign_marker)
        workspace_id = UUID(created["workspace"]["id"])
        owner_email = _bootstrap_payload(marker)["owner_email"]
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            foreign_repository_id = await session.scalar(
                select(Repository.id).where(
                    Repository.workspace_id == UUID(foreign["workspace"]["id"]),
                    Repository.full_name == "qtwin-io/founderos-api",
                )
            )
            assert foreign_repository_id is not None
            deleted_source = SourceRecord(
                workspace_id=workspace_id,
                provider="github",
                external_id="qtwin-io/deleted-evidence",
                record_type="repository",
                source_url="https://github.com/qtwin-io/deleted-evidence",
                payload={},
                payload_hash=f"deleted-{marker}",
                observed_at=now,
                source_updated_at=now,
                is_deleted=True,
                tombstoned_at=now,
                tombstone_observed_at=now,
                tombstone_reason="test_deleted_evidence",
            )
            session.add(deleted_source)
            await session.commit()
            deleted_source_id = deleted_source.id

        cases = {
            "fabricated": _proposal_payload(
                title="Fabricated evidence",
                payload={
                    "repository_full_name": "qtwin-io/fabricated",
                    "title": "Do not approve",
                },
                evidence_refs=[
                    {
                        "kind": "repository",
                        "source": "github",
                        "ref": "qtwin-io/fabricated",
                        "url": None,
                    }
                ],
            ),
            "deleted": _proposal_payload(
                title="Deleted evidence",
                payload={
                    "repository_full_name": "qtwin-io/deleted-evidence",
                    "title": "Do not approve",
                },
                evidence_refs=[
                    {
                        "kind": "repository",
                        "source": "github",
                        "source_record_id": str(deleted_source_id),
                        "url": None,
                    }
                ],
            ),
            "unrelated": _proposal_payload(
                title="Unrelated evidence",
                payload={
                    "repository_full_name": "qtwin-io/another-target",
                    "title": "Do not approve",
                },
            ),
            "cross_workspace": _proposal_payload(
                title="Foreign evidence",
                evidence_refs=[
                    {
                        "kind": "repository",
                        "source": "github",
                        "ref": str(foreign_repository_id),
                        "url": None,
                    }
                ],
            ),
        }
        proposals = {
            name: await _post_proposal(
                created["workspace"]["id"],
                owner_email,
                payload=payload,
            )
            for name, payload in cases.items()
        }

        async with _async_client() as client:
            responses = {
                name: await client.post(
                    f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/approve",
                    headers=_headers(),
                    params={"owner_email": owner_email},
                    json=_decision_payload(proposal),
                )
                for name, proposal in proposals.items()
            }

        assert all(response.status_code == 409 for response in responses.values())
        assert "missing, inactive, unsupported" in responses["fabricated"].json()["detail"]
        assert "missing, inactive, unsupported" in responses["deleted"].json()["detail"]
        assert "unrelated" in responses["unrelated"].json()["detail"]
        assert "outside the workspace" in responses["cross_workspace"].json()["detail"]
        async with AsyncSessionLocal() as session:
            stored = list(
                (
                    await session.scalars(
                        select(ActionProposal).where(
                            ActionProposal.id.in_(
                                [UUID(proposal["id"]) for proposal in proposals.values()]
                            )
                        )
                    )
                ).all()
            )
            event_count = await session.scalar(
                select(func.count())
                .select_from(ActionExecutionEvent)
                .where(
                    ActionExecutionEvent.action_proposal_id.in_(
                        [UUID(proposal["id"]) for proposal in proposals.values()]
                    )
                )
            )
        assert {proposal.status for proposal in stored} == {
            ACTION_PROPOSAL_STATUS_PROPOSED
        }
        assert event_count == 0
    finally:
        await _cleanup_action_fixture(marker)
        await _cleanup_action_fixture(foreign_marker)


async def test_system_approval_requires_exact_headquarters_snapshot(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        owner_email = _bootstrap_payload(marker)["owner_email"]
        async with AsyncSessionLocal() as session:
            owner_id = await session.scalar(select(User.id).where(User.email == owner_email))
            assert owner_id is not None
            proposal = ActionProposal(
                workspace_id=workspace_id,
                target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                action_type=ACTION_TYPE_INTERNAL_TODO,
                title="System proposal requires snapshot",
                payload={"source": "test"},
                evidence_refs=[
                    {
                        "kind": "repository",
                        "source": "github",
                        "ref": "qtwin-io/founderos-api",
                        "url": None,
                    }
                ],
                created_by="system",
            )
            session.add(proposal)
            await session.flush()
            proposal_version = action_proposal_version(proposal)
            with pytest.raises(
                ActionProposalDecisionConflictError,
                match="require an exact headquarters snapshot",
            ):
                await decide_action_proposal(
                    session,
                    workspace_id=workspace_id,
                    proposal_id=proposal.id,
                    actor_user_id=owner_id,
                    command=ActionProposalDecisionCommand(
                        decision="approved",
                        idempotency_key=f"system-without-snapshot-{marker}",
                        proposal_version=proposal_version,
                    ),
                )
            assert proposal.status == ACTION_PROPOSAL_STATUS_PROPOSED
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
                json=_decision_payload(proposal),
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_action_fixture(marker)


async def test_decision_service_rechecks_admin_role_in_write_session(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        member_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_MEMBER,
            suffix="write-session-member",
        )
        proposal = await _post_proposal(created["workspace"]["id"], owner_email)
        async with AsyncSessionLocal() as session:
            member_id = await session.scalar(
                select(User.id).where(User.email == member_email)
            )
            assert member_id is not None
            with pytest.raises(
                ActionProposalDecisionForbiddenError,
                match="insufficient workspace role",
            ):
                await decide_action_proposal(
                    session,
                    workspace_id=UUID(created["workspace"]["id"]),
                    proposal_id=UUID(proposal["id"]),
                    actor_user_id=member_id,
                    command=ActionProposalDecisionCommand(
                        decision="approved",
                        idempotency_key=f"direct-role-check-{uuid4()}",
                        proposal_version=proposal["proposal_version"],
                    ),
                )
    finally:
        await _cleanup_action_fixture(marker)


async def _run_contended_approval_decisions(
    monkeypatch,
    *,
    workspace_id: UUID,
    proposal: dict,
    actor_user_ids: list[UUID],
    idempotency_keys: list[str],
) -> tuple[list[dict[str, object]], int]:
    original_require_current_admin = (
        action_proposal_decision_service._require_current_admin
    )
    both_admin_checks_completed = asyncio.Event()
    arrival_count = 0

    async def synchronized_require_current_admin(*args, **kwargs) -> None:
        nonlocal arrival_count
        await original_require_current_admin(*args, **kwargs)
        arrival_count += 1
        if arrival_count == len(actor_user_ids):
            both_admin_checks_completed.set()
        await asyncio.wait_for(both_admin_checks_completed.wait(), timeout=5)

    monkeypatch.setattr(
        action_proposal_decision_service,
        "_require_current_admin",
        synchronized_require_current_admin,
    )

    async def decide(actor_user_id: UUID, idempotency_key: str) -> dict[str, object]:
        async with AsyncSessionLocal() as session:
            try:
                result = await decide_action_proposal(
                    session,
                    workspace_id=workspace_id,
                    proposal_id=UUID(proposal["id"]),
                    actor_user_id=actor_user_id,
                    command=ActionProposalDecisionCommand(
                        decision="approved",
                        idempotency_key=idempotency_key,
                        proposal_version=proposal["proposal_version"],
                    ),
                )
                outcome: dict[str, object] = {
                    "kind": "success",
                    "event_id": result.event.id,
                    "proposal_status": result.proposal.status,
                    "replayed": result.replayed,
                }
                await session.commit()
                return outcome
            except ActionProposalDecisionConflictError as exc:
                await session.rollback()
                return {"kind": "conflict", "detail": exc.detail}

    outcomes = await asyncio.gather(
        *(
            decide(actor_user_id, idempotency_key)
            for actor_user_id, idempotency_key in zip(
                actor_user_ids,
                idempotency_keys,
                strict=True,
            )
        )
    )
    return outcomes, arrival_count


async def test_concurrent_same_key_decisions_transition_once_and_replay(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        owner_email = _bootstrap_payload(marker)["owner_email"]
        admin_email = await _add_workspace_user(
            str(workspace_id),
            marker,
            role=MEMBERSHIP_ROLE_ADMIN,
            suffix="contention-admin",
        )
        proposal = await _post_proposal(str(workspace_id), owner_email)
        async with AsyncSessionLocal() as session:
            actor_rows = (
                await session.execute(
                    select(User.email, User.id).where(
                        User.email.in_([owner_email, admin_email])
                    )
                )
            ).all()
        actor_ids_by_email = {email: user_id for email, user_id in actor_rows}
        actor_user_ids = [
            actor_ids_by_email[owner_email],
            actor_ids_by_email[admin_email],
        ]
        shared_key = f"concurrent-same-{uuid4()}"

        outcomes, arrival_count = await _run_contended_approval_decisions(
            monkeypatch,
            workspace_id=workspace_id,
            proposal=proposal,
            actor_user_ids=actor_user_ids,
            idempotency_keys=[shared_key, shared_key],
        )

        assert arrival_count == 2
        assert [outcome["kind"] for outcome in outcomes] == ["success", "success"]
        assert sorted(outcome["replayed"] for outcome in outcomes) == [False, True]
        assert len({outcome["event_id"] for outcome in outcomes}) == 1
        assert {
            outcome["proposal_status"] for outcome in outcomes
        } == {ACTION_PROPOSAL_STATUS_APPROVED}

        async with AsyncSessionLocal() as session:
            stored = await session.get(ActionProposal, UUID(proposal["id"]))
            events = list(
                (
                    await session.scalars(
                        select(ActionExecutionEvent).where(
                            ActionExecutionEvent.action_proposal_id
                            == UUID(proposal["id"])
                        )
                    )
                ).all()
            )
        assert stored is not None
        assert stored.status == ACTION_PROPOSAL_STATUS_APPROVED
        assert stored.approved_by_user_id in actor_user_ids
        assert stored.approved_at is not None
        assert len(events) == 1
        assert events[0].id == outcomes[0]["event_id"]
        assert events[0].event_type == ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED
    finally:
        await _cleanup_action_fixture(marker)


async def test_concurrent_different_key_decisions_yield_one_conflict(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = UUID(created["workspace"]["id"])
        owner_email = _bootstrap_payload(marker)["owner_email"]
        admin_email = await _add_workspace_user(
            str(workspace_id),
            marker,
            role=MEMBERSHIP_ROLE_ADMIN,
            suffix="contention-admin",
        )
        proposal = await _post_proposal(str(workspace_id), owner_email)
        async with AsyncSessionLocal() as session:
            actor_rows = (
                await session.execute(
                    select(User.email, User.id).where(
                        User.email.in_([owner_email, admin_email])
                    )
                )
            ).all()
        actor_ids_by_email = {email: user_id for email, user_id in actor_rows}
        actor_user_ids = [
            actor_ids_by_email[owner_email],
            actor_ids_by_email[admin_email],
        ]

        outcomes, arrival_count = await _run_contended_approval_decisions(
            monkeypatch,
            workspace_id=workspace_id,
            proposal=proposal,
            actor_user_ids=actor_user_ids,
            idempotency_keys=[
                f"concurrent-first-{uuid4()}",
                f"concurrent-second-{uuid4()}",
            ],
        )

        successes = [outcome for outcome in outcomes if outcome["kind"] == "success"]
        conflicts = [outcome for outcome in outcomes if outcome["kind"] == "conflict"]
        assert arrival_count == 2
        assert len(successes) == 1
        assert successes[0]["replayed"] is False
        assert successes[0]["proposal_status"] == ACTION_PROPOSAL_STATUS_APPROVED
        assert conflicts == [
            {
                "kind": "conflict",
                "detail": "action proposal is not in proposed status",
            }
        ]

        async with AsyncSessionLocal() as session:
            stored = await session.get(ActionProposal, UUID(proposal["id"]))
            events = list(
                (
                    await session.scalars(
                        select(ActionExecutionEvent).where(
                            ActionExecutionEvent.action_proposal_id
                            == UUID(proposal["id"])
                        )
                    )
                ).all()
            )
        assert stored is not None
        assert stored.status == ACTION_PROPOSAL_STATUS_APPROVED
        assert stored.approved_by_user_id in actor_user_ids
        assert stored.approved_at is not None
        assert len(events) == 1
        assert events[0].id == successes[0]["event_id"]
        assert events[0].event_type == ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED
    finally:
        await _cleanup_action_fixture(marker)


async def test_single_decisions_replay_same_intent_and_reject_conflicts(monkeypatch) -> None:
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
            approve_key = f"approve-{uuid4()}"
            approve_payload = _decision_payload(
                approved,
                idempotency_key=approve_key,
            )
            approve_once = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=approve_payload,
            )
            approve_twice = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=approve_payload,
            )
            approve_with_new_key = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=_decision_payload(approved),
            )
            reject_key = f"reject-{uuid4()}"
            reject_payload = _decision_payload(
                rejected,
                idempotency_key=reject_key,
                reason="Not needed",
            )
            reject_once = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{rejected['id']}/reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=reject_payload,
            )
            reject_twice = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{rejected['id']}/reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=reject_payload,
            )
            reject_approved = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approved['id']}/reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=_decision_payload(
                    approved,
                    idempotency_key=approve_key,
                    reason="Too late",
                ),
            )

        assert approve_once.status_code == 200
        assert approve_twice.status_code == 200
        assert approve_twice.json()["decision_receipt"]["replayed"] is True
        assert (
            approve_twice.json()["decision_receipt"]["receipt_id"]
            == approve_once.json()["decision_receipt"]["receipt_id"]
        )
        assert approve_with_new_key.status_code == 409
        assert approve_with_new_key.json() == {
            "detail": "action proposal is not in proposed status"
        }
        assert reject_once.status_code == 200
        assert reject_once.json()["proposal"]["status"] == ACTION_PROPOSAL_STATUS_REJECTED
        assert reject_once.json()["proposal"]["rejection_reason"] == "Not needed"
        assert reject_twice.status_code == 200
        assert reject_twice.json()["decision_receipt"]["replayed"] is True
        assert (
            reject_twice.json()["decision_receipt"]["receipt_id"]
            == reject_once.json()["decision_receipt"]["receipt_id"]
        )
        assert reject_approved.status_code == 409
        assert reject_approved.json() == {
            "detail": "idempotency key was already used with different decision input"
        }
    finally:
        await _cleanup_action_fixture(marker)


async def test_single_decision_rejects_stale_proposal_version_without_audit(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        proposal = await _post_proposal(created["workspace"]["id"], owner_email)
        async with AsyncSessionLocal() as session:
            stored = await session.get(ActionProposal, UUID(proposal["id"]))
            assert stored is not None
            stored.title = "Changed after the actor opened the decision"
            await session.commit()

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{proposal['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=_decision_payload(proposal),
            )

        assert response.status_code == 409
        assert response.json() == {"detail": "action proposal version changed"}
        async with AsyncSessionLocal() as session:
            stored = await session.get(ActionProposal, UUID(proposal["id"]))
            assert stored is not None
            assert stored.status == ACTION_PROPOSAL_STATUS_PROPOSED
            event_count = await session.scalar(
                select(func.count())
                .select_from(ActionExecutionEvent)
                .where(ActionExecutionEvent.action_proposal_id == stored.id)
            )
        assert event_count == 0
    finally:
        await _cleanup_action_fixture(marker)


async def test_bulk_approve_partially_succeeds_without_execution(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        approve_me = await _post_proposal(created["workspace"]["id"], owner_email)
        already_approved = await _post_proposal(
            created["workspace"]["id"],
            owner_email,
            payload=_proposal_payload(title="Already approved"),
        )
        missing_id = uuid4()
        async with _async_client() as client:
            approved_once = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{already_approved['id']}/approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=_decision_payload(already_approved),
            )
        assert approved_once.status_code == 200
        executions_before = await _count(ActionExecution)
        bulk_payload = {
            "decisions": [
                _bulk_decision_item(approve_me),
                _bulk_decision_item(already_approved),
                {
                    "proposal_id": str(missing_id),
                    "idempotency_key": f"bulk-missing-{uuid4()}",
                    "proposal_version": f"ap1_{'0' * 64}",
                },
            ]
        }

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/bulk-approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=bulk_payload,
            )
            replay = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/bulk-approve",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=bulk_payload,
            )
            approve_me_audit = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{approve_me['id']}/audit",
                headers=_headers(),
                params={"owner_email": owner_email},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["succeeded_count"] == 1
        assert body["failed_count"] == 2
        assert body["is_live"] is False
        assert body["execution_started"] is False
        assert body["proposals"][0]["id"] == approve_me["id"]
        assert body["proposals"][0]["status"] == ACTION_PROPOSAL_STATUS_APPROVED
        assert len(body["decision_receipts"]) == 1
        assert body["decision_receipts"][0]["proposal_id"] == approve_me["id"]
        assert body["decision_receipts"][0]["proposal_version"] == (
            approve_me["proposal_version"]
        )
        assert replay.status_code == 200, replay.text
        replay_body = replay.json()
        assert replay_body["succeeded_count"] == 1
        assert replay_body["failed_count"] == 2
        assert replay_body["decision_receipts"][0]["proposal_id"] == approve_me["id"]
        assert replay_body["decision_receipts"][0]["receipt_id"] == (
            body["decision_receipts"][0]["receipt_id"]
        )
        assert replay_body["decision_receipts"][0]["replayed"] is True
        assert [failure["status_code"] for failure in body["failures"]] == [409, 404]
        assert body["failures"][0]["proposal_id"] == already_approved["id"]
        assert body["failures"][1]["proposal_id"] == str(missing_id)
        assert any("deferred" in warning for warning in body["warnings"])
        assert any("does not execute provider actions" in warning for warning in body["warnings"])
        assert await _count(ActionExecution) == executions_before
        assert approve_me_audit.status_code == 200, approve_me_audit.text
        approve_audit = approve_me_audit.json()
        assert (
            approve_audit["events"][0]["event_type"]
            == ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED
        )
        assert approve_audit["events"][0]["event_metadata"]["decision"] == "approved"
        assert approve_audit["events"][0]["event_metadata"]["bulk"] is True
        assert approve_audit["events"][0]["external_execution_enabled"] is False
        assert approve_audit["receipt"]["external_write_performed"] is False
    finally:
        await _cleanup_action_fixture(marker)


async def test_bulk_reject_succeeds_without_execution(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        owner_email = _bootstrap_payload(marker)["owner_email"]
        first = await _post_proposal(created["workspace"]["id"], owner_email)
        second = await _post_proposal(
            created["workspace"]["id"],
            owner_email,
            payload=_proposal_payload(title="Reject second"),
        )
        executions_before = await _count(ActionExecution)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/bulk-reject",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "decisions": [
                        _bulk_decision_item(first),
                        _bulk_decision_item(second),
                    ],
                    "reason": "Not now",
                },
            )
            first_audit = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/{first['id']}/audit",
                headers=_headers(),
                params={"owner_email": owner_email},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["succeeded_count"] == 2
        assert body["failed_count"] == 0
        assert body["failures"] == []
        assert len(body["decision_receipts"]) == 2
        assert body["execution_started"] is False
        assert {proposal["id"] for proposal in body["proposals"]} == {
            first["id"],
            second["id"],
        }
        assert {
            proposal["status"] for proposal in body["proposals"]
        } == {ACTION_PROPOSAL_STATUS_REJECTED}
        assert {
            proposal["rejection_reason"] for proposal in body["proposals"]
        } == {"Not now"}
        assert await _count(ActionExecution) == executions_before
        assert first_audit.status_code == 200, first_audit.text
        first_audit_body = first_audit.json()
        assert (
            first_audit_body["events"][0]["event_type"]
            == ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED
        )
        assert first_audit_body["events"][0]["event_metadata"]["decision"] == "rejected"
        assert first_audit_body["events"][0]["event_metadata"]["bulk"] is True
        assert first_audit_body["events"][0]["external_execution_enabled"] is False
        assert first_audit_body["receipt"]["external_write_performed"] is False
    finally:
        await _cleanup_action_fixture(marker)


async def test_member_cannot_bulk_approve(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_action_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        member_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_MEMBER,
            suffix="bulk-member",
        )
        proposal = await _post_proposal(
            created["workspace"]["id"],
            _bootstrap_payload(marker)["owner_email"],
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/actions/proposals/bulk-approve",
                headers=_headers(),
                params={"owner_email": member_email},
                json={"decisions": [_bulk_decision_item(proposal)]},
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
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
