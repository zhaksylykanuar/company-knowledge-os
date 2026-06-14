from __future__ import annotations

import json

import pytest

from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal
from app.services.connector_clients import (
    ConnectorClientNotEnabledError,
    LiveEmailReadOnlyProvider,
)
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.data_quality_center import build_data_quality_center
from app.services.secret_patterns import contains_secret_value
from app.services.source_connectors import NoopSourceConnector


async def test_gmail_local_only_ingest_works_without_raw_body() -> None:
    async with AsyncSessionLocal() as session:
        connector = NoopSourceConnector("gmail", session=session)
        result = await connector.sync()
    assert result.status == "succeeded"
    assert result.sanitized_summary.get("mode") == "local_records"
    for event in result.events:
        payload = event.safe_payload()
        for key in payload:
            assert "body" not in str(key).lower()
            assert "html" not in str(key).lower()
        assert "raw://" not in json.dumps(payload)


async def test_gmail_oauth_provider_refuses_no_fake_connected() -> None:
    provider = LiveEmailReadOnlyProvider()
    with pytest.raises(ConnectorClientNotEnabledError):
        await provider.test_connection()
    with pytest.raises(ConnectorClientNotEnabledError):
        await provider.list_threads()


async def test_diagnostics_reports_real_execution_and_email_stance() -> None:
    async with AsyncSessionLocal() as session:
        diagnostics = await build_connector_diagnostics(session)
    assert "real_execution_enabled" in diagnostics
    by_type = {c["source_type"]: c for c in diagnostics["connectors"]}

    jira = by_type["jira"]
    github = by_type["github"]
    assert jira["real_execution"] in {"enabled", "disabled"}
    assert github["real_execution"] in {"enabled", "disabled"}
    if not diagnostics["real_execution_enabled"]:
        assert jira["adapter_type"] == "real-disabled"
        assert github["adapter_type"] == "real-disabled"

    gmail = by_type["gmail"]
    assert gmail["real_execution"] == "local_only"
    assert gmail["adapter_type"] in {"local_only", "noop"}
    # No fake connected for gmail.
    if gmail["connector_state"] == "connected":
        assert gmail["last_success_at"] is not None

    # Per-connector event counts are present.
    assert "events_ingested" in jira
    assert "normalized_events" in jira
    # Still no secret values anywhere.
    assert not contains_secret_value(json.dumps(diagnostics))


async def test_data_quality_flags_configured_but_real_disabled(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "enable_real_connectors", False)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage15-fake-token-value")
    async with AsyncSessionLocal() as session:
        center = await build_data_quality_center(session)
    issues = [
        issue
        for issue in center["issues"]
        if issue["category"] == "connector_real_execution_disabled"
    ]
    assert any(issue["affected_source"] == "jira" for issue in issues)
    for issue in issues:
        assert issue["severity"] == "low"
        assert issue["cta"]["action"] == "enable_real_connectors"
