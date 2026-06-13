from __future__ import annotations

import json

import pytest

from app.services.connector_clients import (
    ConnectorClientNotEnabledError,
    EmailReadOnlyConnectorClient,
    GitHubReadOnlyConnectorClient,
    JiraReadOnlyConnectorClient,
    LiveEmailReadOnlyProvider,
    LiveGitHubReadOnlyProvider,
    LiveJiraReadOnlyProvider,
    ReadOnlyRecord,
    live_connector_clients,
)


class _FakeJiraProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def test_connection(self) -> dict:
        self.calls += 1
        return {"status": "ok", "checked": "jira"}

    async def list_updated_issues(self, *, since=None, limit=50):
        self.calls += 1
        return [
            ReadOnlyRecord(
                external_id="ALPHA-1",
                object_type="issue",
                event_type="jira.issue.updated",
                title="Issue title",
                summary="Issue summary",
                actor="Person A",
                url="https://example.invalid/ALPHA-1",
                metadata={"project": "ALPHA", "secret_token": "should-be-redacted"},
            )
        ]

    async def list_project_issues(self, *, project=None, since=None, limit=200):
        return await self.list_updated_issues()


class _FakeGitHubProvider:
    async def test_connection(self) -> dict:
        return {"status": "ok", "checked": "github"}

    async def list_repo_activity(self, *, since=None, limit=50):
        return [
            ReadOnlyRecord(
                external_id="org/repo#1",
                object_type="pull_request",
                event_type="github.pull_request.synchronized",
                title="PR",
            )
        ]

    async def list_pull_requests(self, *, since=None, limit=50):
        return await self.list_repo_activity()

    async def list_commits(self, *, since=None, limit=50):
        return [
            ReadOnlyRecord(
                external_id="org/repo@abc",
                object_type="commit",
                event_type="github.commit.recorded",
                title="commit",
            )
        ]


class _FakeEmailProvider:
    async def test_connection(self) -> dict:
        return {"status": "ok", "checked": "gmail"}

    async def list_threads(self, *, since=None, limit=50):
        return [
            ReadOnlyRecord(
                external_id="thread-1",
                object_type="message",
                event_type="gmail.message.ingested",
                title="Subject",
                summary="thread summary",
            )
        ]


def test_read_only_record_has_no_body_field() -> None:
    record = ReadOnlyRecord(
        external_id="x", object_type="issue", event_type="e"
    )
    assert not hasattr(record, "body")
    assert not hasattr(record, "raw_body")
    assert not hasattr(record, "raw")


async def test_jira_client_maps_records_without_raw_body() -> None:
    provider = _FakeJiraProvider()
    client = JiraReadOnlyConnectorClient(provider)

    check = await client.test_connection("jira")
    assert check["status"] == "ok"

    events = await client.sync_events("jira", watermark=None)
    assert len(events) == 1
    event = events[0]
    assert event.source_type == "jira"
    assert event.object_type == "issue"
    payload = event.safe_payload()
    blob = json.dumps(payload)
    assert "body" not in payload
    assert "raw_body" not in payload
    # sensitive-looking metadata is redacted, never passed through raw.
    assert "should-be-redacted" not in blob

    backfilled = await client.backfill_events("jira", limit=5)
    assert len(backfilled) == 1


async def test_github_client_sync_and_backfill_are_read_only() -> None:
    client = GitHubReadOnlyConnectorClient(_FakeGitHubProvider())
    sync_events = await client.sync_events("github")
    assert [e.object_type for e in sync_events] == ["pull_request"]
    backfill_events = await client.backfill_events("github", limit=10)
    assert {e.object_type for e in backfill_events} == {"pull_request", "commit"}


async def test_email_client_threads_have_no_body() -> None:
    client = EmailReadOnlyConnectorClient(_FakeEmailProvider())
    events = await client.sync_events("gmail")
    assert len(events) == 1
    assert "body" not in events[0].safe_payload()


async def test_live_providers_refuse_without_enablement() -> None:
    jira = LiveJiraReadOnlyProvider()
    github = LiveGitHubReadOnlyProvider()
    email = LiveEmailReadOnlyProvider()

    with pytest.raises(ConnectorClientNotEnabledError):
        await jira.test_connection()
    with pytest.raises(ConnectorClientNotEnabledError):
        await jira.list_updated_issues()
    with pytest.raises(ConnectorClientNotEnabledError):
        await jira.list_project_issues()
    with pytest.raises(ConnectorClientNotEnabledError):
        await github.test_connection()
    with pytest.raises(ConnectorClientNotEnabledError):
        await github.list_repo_activity()
    with pytest.raises(ConnectorClientNotEnabledError):
        await github.list_pull_requests()
    with pytest.raises(ConnectorClientNotEnabledError):
        await github.list_commits()
    with pytest.raises(ConnectorClientNotEnabledError):
        await email.test_connection()
    with pytest.raises(ConnectorClientNotEnabledError):
        await email.list_threads()


async def test_live_connector_clients_are_not_wired_live() -> None:
    clients = live_connector_clients()
    assert set(clients) == {"jira", "github", "gmail"}
    # Every live client still refuses (no network) until explicitly enabled.
    with pytest.raises(ConnectorClientNotEnabledError):
        await clients["jira"].test_connection("jira")


def test_connector_client_not_enabled_error_reason_code() -> None:
    err = ConnectorClientNotEnabledError("jira_live_connector_disabled")
    assert err.reason_code == "jira_live_connector_disabled"
