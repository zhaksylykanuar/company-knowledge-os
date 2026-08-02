from __future__ import annotations

from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import WorkspaceAIConfiguration
from app.main import app
from app.services import ai_settings_service
from app.services.ai_settings_service import (
    AssistantRuntimeConfiguration,
    resolve_assistant_runtime_configuration,
)
from app.services.assistant_llm_service import (
    ValidatedAssistantReasoning,
    ValidatedAssistantSection,
)
from app.services.secret_encryption import decrypt_secret


TEST_AI_KEY = "test-ai-settings-provider-key"


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(
        settings,
        "secret_encryption_key",
        SecretStr("test-ai-settings-encryption-key"),
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")
    monkeypatch.setattr(settings, "enable_llm", True)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace(marker: str) -> tuple[User, Workspace, User]:
    async with AsyncSessionLocal() as session:
        owner = User(
            email=f"ai-settings-{marker}@example.test",
            name="AI Settings Owner",
        )
        viewer = User(
            email=f"ai-settings-{marker}-viewer@example.test",
            name="AI Settings Viewer",
        )
        session.add_all([owner, viewer])
        await session.flush()
        workspace = Workspace(
            name=f"AI Settings {marker}",
            slug=f"ai-settings-{marker}",
            created_by_user_id=owner.id,
        )
        session.add(workspace)
        await session.flush()
        session.add_all(
            [
                Membership(
                    workspace_id=workspace.id,
                    user_id=owner.id,
                    role=MEMBERSHIP_ROLE_OWNER,
                ),
                Membership(
                    workspace_id=workspace.id,
                    user_id=viewer.id,
                    role=MEMBERSHIP_ROLE_VIEWER,
                ),
            ]
        )
        await session.commit()
        return owner, workspace, viewer


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.scalars(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"ai-settings-{marker}%")
                    )
                )
            ).all()
        )
        user_ids = list(
            (
                await session.scalars(
                    select(User.id).where(
                        User.email.like(f"ai-settings-{marker}%@example.test")
                    )
                )
            ).all()
        )
        if workspace_ids:
            await session.execute(
                delete(WorkspaceAIConfiguration).where(
                    WorkspaceAIConfiguration.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


def _path(workspace_id: UUID, suffix: str = "") -> str:
    return f"/api/v1/workspaces/{workspace_id}/ai-settings{suffix}"


def _configuration_payload(**overrides) -> dict:
    payload = {
        "enabled": True,
        "data_policy_acknowledged": True,
        "model": "gpt-5.6",
        "reasoning_effort": "medium",
        "max_output_tokens": 1_200,
        "api_key": TEST_AI_KEY,
    }
    payload.update(overrides)
    return payload


async def test_ai_key_is_encrypted_and_never_returned(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with _client() as client:
            response = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_configuration_payload(),
            )
            read = await client.get(
                _path(workspace.id),
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        body = response.json()
        assert body["contract"] == "ai-settings.v1"
        assert body["configured"] is True
        assert body["enabled"] is True
        assert body["key_present"] is True
        assert body["data_policy"]["acknowledged"] is True
        assert body["last_check"] is None
        assert body["boundary"] == {
            "provider_call_on_apply": False,
            "company_data_sent_during_check": False,
            "stored_secret_returned": False,
            "chat_persisted": False,
            "external_writes": False,
        }
        assert TEST_AI_KEY not in response.text
        assert "encrypted_api_key" not in response.text
        assert read.status_code == 200
        assert read.headers["cache-control"] == "private, no-store"
        assert TEST_AI_KEY not in read.text

        async with AsyncSessionLocal() as session:
            configuration = await session.scalar(
                select(WorkspaceAIConfiguration).where(
                    WorkspaceAIConfiguration.workspace_id == workspace.id
                )
            )
            assert configuration is not None
            assert configuration.encrypted_api_key is not None
            assert configuration.encrypted_api_key.startswith("fernet:v2:")
            assert decrypt_secret(configuration.encrypted_api_key) == TEST_AI_KEY
            assert TEST_AI_KEY not in repr(configuration)
    finally:
        await _cleanup(marker)


async def test_connection_check_sends_no_company_data_and_persists_safe_receipt(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    captured: dict = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        fact = kwargs["facts"][0]
        section = ValidatedAssistantSection(
            text=fact.text,
            citation_ids=fact.citation_ids,
        )
        return ValidatedAssistantReasoning(
            fact=section,
            interpretation=ValidatedAssistantSection(None, ()),
            objection=ValidatedAssistantSection(None, ()),
            recommendation=ValidatedAssistantSection(None, ()),
        )

    monkeypatch.setattr(ai_settings_service, "generate_assistant_reasoning", fake_generate)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with _client() as client:
            applied = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_configuration_payload(),
            )
            checked = await client.post(
                _path(workspace.id, "/check"),
                headers=_headers(),
                params={"owner_email": owner.email},
            )
            read = await client.get(
                _path(workspace.id),
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert applied.status_code == 200, applied.text
        assert checked.status_code == 200, checked.text
        assert checked.headers["cache-control"] == "private, no-store"
        assert checked.json() == {
            "status": "passed",
            "code": "connection_verified",
            "message": "The provider returned a strict evidence-bound response.",
            "checked_at": checked.json()["checked_at"],
            "model": "gpt-5.6",
            "provider_call_performed": True,
            "company_data_sent": False,
            "external_write_performed": False,
        }
        assert len(captured["facts"]) == 1
        assert captured["facts"][0].text == (
            "FounderOS AI connection check uses no company facts."
        )
        assert workspace.name not in str(captured)
        assert owner.email not in str(captured)
        assert captured["api_key"] == TEST_AI_KEY
        assert read.json()["last_check"]["status"] == "passed"
        assert TEST_AI_KEY not in read.text
    finally:
        await _cleanup(marker)


async def test_connection_check_rejects_a_stale_configuration_result(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)

    async def fake_generate(**_kwargs):
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(WorkspaceAIConfiguration).where(
                    WorkspaceAIConfiguration.workspace_id == workspace.id
                )
            )
            assert row is not None
            row.model = "gpt-5.6-terra"
            row.configuration_version += 1
            await session.commit()
        return ValidatedAssistantReasoning(
            fact=ValidatedAssistantSection(
                "FounderOS AI connection check uses no company facts.",
                ("internal:ai-settings-check",),
            ),
            interpretation=ValidatedAssistantSection(None, ()),
            objection=ValidatedAssistantSection(None, ()),
            recommendation=ValidatedAssistantSection(None, ()),
        )

    monkeypatch.setattr(ai_settings_service, "generate_assistant_reasoning", fake_generate)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with _client() as client:
            applied = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_configuration_payload(),
            )
            checked = await client.post(
                _path(workspace.id, "/check"),
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert applied.status_code == 200
        assert checked.status_code == 200
        assert checked.json()["code"] == "configuration_changed"
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(WorkspaceAIConfiguration).where(
                    WorkspaceAIConfiguration.workspace_id == workspace.id
                )
            )
            assert row is not None
            assert row.model == "gpt-5.6-terra"
            assert row.last_check_status is None
    finally:
        await _cleanup(marker)


async def test_runtime_prefers_verified_workspace_configuration(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            result = await ai_settings_service.save_workspace_ai_settings(
                session,
                workspace_id=workspace.id,
                requested_by_user_id=owner.id,
                payload=ai_settings_service.AISettingsInput(
                    enabled=True,
                    data_policy_acknowledged=True,
                    model="gpt-5.6-terra",
                    reasoning_effort="low",
                    max_output_tokens=900,
                    api_key=TEST_AI_KEY,
                ),
            )
            assert result["configured"] is True
            row = await session.scalar(
                select(WorkspaceAIConfiguration).where(
                    WorkspaceAIConfiguration.workspace_id == workspace.id
                )
            )
            assert row is not None
            row.last_check_status = "passed"
            row.last_check_code = "connection_verified"
            row.last_checked_at = ai_settings_service._utcnow()
            row.last_check_model = row.model
            await session.commit()

        resolution = await resolve_assistant_runtime_configuration(
            workspace_id=workspace.id
        )

        assert isinstance(resolution.configuration, AssistantRuntimeConfiguration)
        assert resolution.warning is None
        assert resolution.configuration.api_key == TEST_AI_KEY
        assert resolution.configuration.model == "gpt-5.6-terra"
        assert resolution.configuration.reasoning_effort == "low"
        assert resolution.configuration.max_output_tokens == 900
    finally:
        await _cleanup(marker)


async def test_workspace_configuration_never_falls_back_to_environment_key(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            await ai_settings_service.save_workspace_ai_settings(
                session,
                workspace_id=workspace.id,
                requested_by_user_id=owner.id,
                payload=ai_settings_service.AISettingsInput(
                    enabled=True,
                    data_policy_acknowledged=True,
                    model="gpt-5.6",
                    reasoning_effort="medium",
                    max_output_tokens=1_200,
                    api_key=TEST_AI_KEY,
                ),
            )
            await session.commit()

        resolution = await resolve_assistant_runtime_configuration(
            workspace_id=workspace.id
        )

        assert resolution.configuration is None
        assert resolution.warning == "ai_not_verified"
    finally:
        await _cleanup(marker)


async def test_missing_workspace_ai_configuration_stays_deterministic(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-environment-key")
    await _cleanup(marker)
    try:
        _owner, workspace, _viewer = await _seed_workspace(marker)

        resolution = await resolve_assistant_runtime_configuration(
            workspace_id=workspace.id
        )

        assert resolution.configuration is None
        assert resolution.warning == "ai_not_configured"
    finally:
        await _cleanup(marker)


async def test_database_rejects_enabled_ai_without_an_encrypted_key(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        _owner, workspace, _viewer = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            session.add(
                WorkspaceAIConfiguration(
                    workspace_id=workspace.id,
                    enabled=True,
                    model="gpt-5.6",
                    data_policy_version=ai_settings_service.AI_DATA_POLICY_VERSION,
                    data_policy_acknowledged_at=ai_settings_service._utcnow(),
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            else:
                raise AssertionError("database accepted enabled AI without a key")
    finally:
        await _cleanup(marker)


async def test_enable_requires_key_policy_and_verification_stays_explicit(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with _client() as client:
            missing_key = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_configuration_payload(api_key=None),
            )
            missing_policy = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_configuration_payload(data_policy_acknowledged=False),
            )
            monkeypatch.setattr(settings, "enable_llm", False)
            disabled_gate = await client.post(
                _path(workspace.id, "/check"),
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert missing_key.status_code == 409
        assert missing_key.headers["cache-control"] == "private, no-store"
        assert missing_policy.status_code == 409
        assert missing_policy.headers["cache-control"] == "private, no-store"
        assert disabled_gate.status_code == 200
        assert disabled_gate.headers["cache-control"] == "private, no-store"
        assert disabled_gate.json()["code"] == "server_gate_disabled"
        assert disabled_gate.json()["provider_call_performed"] is False
    finally:
        await _cleanup(marker)


async def test_viewer_is_read_only_and_cross_workspace_fails_closed(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, viewer = await _seed_workspace(marker)
        other_owner, _other_workspace, _ = await _seed_workspace(f"{marker}-other")
        async with _client() as client:
            viewer_read = await client.get(
                _path(workspace.id),
                headers=_headers(),
                params={"owner_email": viewer.email},
            )
            viewer_save = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": viewer.email},
                json=_configuration_payload(),
            )
            viewer_check = await client.post(
                _path(workspace.id, "/check"),
                headers=_headers(),
                params={"owner_email": viewer.email},
            )
            cross_read = await client.get(
                _path(workspace.id),
                headers=_headers(),
                params={"owner_email": other_owner.email},
            )

        assert viewer_read.status_code == 200
        assert viewer_save.status_code == 403
        assert viewer_save.headers["cache-control"] == "private, no-store"
        assert viewer_check.status_code == 403
        assert viewer_check.headers["cache-control"] == "private, no-store"
        assert cross_read.status_code == 404
        assert cross_read.headers["cache-control"] == "private, no-store"
        assert owner.email not in cross_read.text
    finally:
        await _cleanup(marker)
        await _cleanup(f"{marker}-other")


async def test_remove_credential_disables_ai_and_retains_no_secret(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _viewer = await _seed_workspace(marker)
        async with _client() as client:
            applied = await client.post(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_configuration_payload(),
            )
            removed = await client.delete(
                _path(workspace.id, "/configuration"),
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert applied.status_code == 200
        assert removed.status_code == 200
        assert removed.json()["configured"] is False
        assert removed.json()["enabled"] is False
        assert removed.json()["key_present"] is False
        assert removed.json()["data_policy"]["acknowledged"] is False
        assert TEST_AI_KEY not in removed.text
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(WorkspaceAIConfiguration).where(
                    WorkspaceAIConfiguration.workspace_id == workspace.id
                )
            )
            assert row is not None
            assert row.encrypted_api_key is None
            assert row.last_check_status is None
    finally:
        await _cleanup(marker)
