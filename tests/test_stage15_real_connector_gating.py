from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.connector_clients import (
    ConnectorClientNotEnabledError,
    LiveGitHubReadOnlyProvider,
    LiveJiraReadOnlyProvider,
)
from app.services.provider_execution_guard import LIVE_PROVIDER_EXECUTION_ACK
from app.services.source_connectors import default_connector_registry
from app.services.source_run_orchestrator import run_source_request
from tests.test_stage11_connector_ingestion import (
    _cleanup,
    _ensure_tables,
    _restore_state,
    _state_snapshot,
)


def _make_request(source_type: str, action_type: str, marker: str) -> SourceRunRequest:
    return SourceRunRequest(
        request_id=f"src_req_stage15_{marker}_{uuid4().hex[:8]}",
        source_type=source_type,
        action_type=action_type,
        status="requested",
        request_key=f"{source_type}-{action_type}-{marker}",
        correlation_id=f"corr-stage15-{marker}",
        idempotency_key=f"{source_type}:{action_type}:{marker}",
        requested_by="founder",
        requested_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        input_snapshot={"input": {}},
        result_summary={},
        error_summary={},
        external_side_effect=False,
    )


def test_real_connectors_disabled_by_default() -> None:
    assert app_settings.enable_real_connectors is False


def test_default_registry_marks_real_disabled_when_off(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    registry = default_connector_registry()
    for source_type in ("jira", "github"):
        connector = registry[source_type]
        assert connector._real_disabled is True
        assert connector._client is None
    # internal/local sources are unaffected.
    assert registry["declarations"]._real_disabled is False
    assert registry["gmail"]._real_disabled is False


def test_enabling_flag_wires_real_client_boundary(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage15-fake-token-value")
    monkeypatch.setenv("GITHUB_TOKEN", "stage15-fake-token-value")
    monkeypatch.setenv("GITHUB_REPOS", "owner/repo")
    registry = default_connector_registry()
    assert registry["jira"]._real_disabled is False
    assert registry["jira"]._client is not None
    assert registry["github"]._client is not None


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ok": True}


class _FakeAsyncClient:
    calls: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def get(self, url: str, **kwargs) -> _FakeResponse:
        self.calls.append((url, kwargs))
        return _FakeResponse()


async def test_live_providers_never_network_when_disabled(monkeypatch) -> None:
    # Even fully configured, a disabled provider must not touch the network.
    def _boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("network call attempted while disabled")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    jira = LiveJiraReadOnlyProvider(
        base_url="https://example.atlassian.net",
        email="ops@example.com",
        token="stage15-fake-token-value",
        enabled=False,
    )
    github = LiveGitHubReadOnlyProvider(
        token="stage15-fake-token-value", repos=("owner/repo",), enabled=False
    )
    with pytest.raises(ConnectorClientNotEnabledError):
        await jira.test_connection()
    with pytest.raises(ConnectorClientNotEnabledError):
        await jira.list_updated_issues()
    with pytest.raises(ConnectorClientNotEnabledError):
        await github.test_connection()
    with pytest.raises(ConnectorClientNotEnabledError):
        await github.list_pull_requests()


async def test_configured_jira_run_skips_when_real_disabled(monkeypatch) -> None:
    await _ensure_tables()
    # Configure jira fully, but keep real connectors disabled.
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage15-fake-token-value")
    # Any network attempt should fail the test.
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network attempted")),
    )
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("jira", "test", marker)
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session, request=request, run_id=f"src_run_{marker}"
            )
            await session.commit()
        assert result["status"] == "skipped"
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"jira-test-{marker}"
                )
            )
            state = await session.scalar(
                select(SourceControlState).where(
                    SourceControlState.source_type == "jira"
                )
            )
        assert row.result_summary["status"] == "skipped"
        assert (
            row.result_summary["sanitized_summary"]["mode"]
            == "real_connectors_disabled"
        )
        # No fake "connected" from a disabled run.
        assert state is None or state.last_success_at is None
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_request_snapshot_live_ack_does_not_authorize_provider_run(
    monkeypatch,
) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage15-fake-token-value")

    def _boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("network attempted without live provider ack")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("jira", "test", marker)
            request.input_snapshot = {
                "input": {
                    "allow_live_provider_execution": True,
                    "live_provider_ack_supplied": True,
                    "provider_execution_ack_valid": True,
                }
            }
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session, request=request, run_id=f"src_run_{marker}"
            )
            await session.commit()
        assert result["status"] == "skipped"
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"jira-test-{marker}"
                )
            )
        assert row.result_summary["status"] == "skipped"
        assert row.result_summary["sanitized_summary"]["mode"] == (
            "provider_execution_blocked"
        )
        assert row.result_summary["sanitized_summary"]["reason"] == (
            "provider_execution_default_denied"
        )
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


async def test_enabled_jira_run_accepts_runner_live_provider_ack(
    monkeypatch,
) -> None:
    await _ensure_tables()
    monkeypatch.setattr(app_settings, "enable_real_connectors", True)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage15-fake-token-value")
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    try:
        async with AsyncSessionLocal() as session:
            request = _make_request("jira", "test", marker)
            session.add(request)
            await session.flush()
            result = await run_source_request(
                session,
                request=request,
                run_id=f"src_run_{marker}",
                allow_live_provider_execution=True,
                provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
            )
            await session.commit()
        assert result["status"] == "succeeded"
        assert _FakeAsyncClient.calls
        assert _FakeAsyncClient.calls[0][0].endswith("/rest/api/3/myself")
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)
