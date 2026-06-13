"""Read-only adapter client boundary for external connectors.

This module defines the *shape* of read-only provider clients (Jira, GitHub,
email) and adapts them to the orchestrator's ``ReadOnlyConnectorClient``
contract. The boundary is deliberately conservative:

- Provider methods are read-only by name and by contract.
- Providers return ``ReadOnlyRecord`` values that have **no raw body field**,
  so a raw email/issue body cannot structurally leak into a ``ConnectorEvent``.
- The live (real) providers refuse to run until live access is explicitly
  enabled, and they never make a network call from this module. Tests use the
  fake providers only, so the suite never touches a real external API.
- ``NoopSourceConnector`` already gates on readiness, so a client is only ever
  invoked when the source is configured; a missing-config source never reaches
  a client at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.services.browser_config import sanitize_for_logs
from app.services.source_connectors import ConnectorEvent, ReadOnlyConnectorClient

DEFAULT_SYNC_LIMIT = 50
DEFAULT_BACKFILL_LIMIT = 200


class ConnectorClientNotEnabledError(RuntimeError):
    """Raised when a live provider is invoked without explicit enablement.

    Carries a stable ``reason_code`` so the orchestrator can persist a
    sanitized error without exposing provider internals.
    """

    def __init__(self, reason_code: str = "live_connector_disabled") -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ReadOnlyRecord:
    """A safe, read-only projection of an external object.

    Intentionally has no ``body``/``raw`` field: only metadata that is safe to
    mirror into the knowledge graph and Obsidian vault.
    """

    external_id: str
    object_type: str
    event_type: str
    occurred_at: datetime | None = None
    title: str | None = None
    summary: str | None = None
    actor: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _record_to_event(source_type: str, record: ReadOnlyRecord) -> ConnectorEvent:
    metadata = sanitize_for_logs(dict(record.metadata or {}))
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.setdefault("source_type", source_type)
    payload: dict[str, Any] = {
        "source_object_type": record.object_type,
    }
    if record.title:
        payload["title"] = record.title
    if record.summary:
        payload["summary"] = record.summary
    return ConnectorEvent(
        source_type=source_type,
        external_id=record.external_id,
        object_type=record.object_type,
        event_type=record.event_type,
        occurred_at=record.occurred_at,
        title=record.title,
        summary=record.summary,
        actor=record.actor,
        url=record.url,
        sanitized_payload=payload,
        source_metadata=metadata,
    )


# --- Provider protocols (read-only) --------------------------------------


class JiraReadOnlyProvider(Protocol):
    async def test_connection(self) -> dict[str, Any]: ...

    async def list_updated_issues(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]: ...

    async def list_project_issues(
        self,
        *,
        project: str | None = None,
        since: str | None = None,
        limit: int = DEFAULT_BACKFILL_LIMIT,
    ) -> list[ReadOnlyRecord]: ...


class GitHubReadOnlyProvider(Protocol):
    async def test_connection(self) -> dict[str, Any]: ...

    async def list_repo_activity(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]: ...

    async def list_pull_requests(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]: ...

    async def list_commits(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]: ...


class EmailReadOnlyProvider(Protocol):
    async def test_connection(self) -> dict[str, Any]: ...

    async def list_threads(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]: ...


# --- Connector client adapters (ReadOnlyConnectorClient) -----------------


class JiraReadOnlyConnectorClient:
    """Adapts a :class:`JiraReadOnlyProvider` to the connector contract."""

    def __init__(self, provider: JiraReadOnlyProvider) -> None:
        self._provider = provider

    async def test_connection(self, source_type: str) -> dict[str, Any]:
        return sanitize_for_logs(await self._provider.test_connection())

    async def sync_events(
        self, source_type: str, *, watermark: str | None = None
    ) -> list[ConnectorEvent]:
        records = await self._provider.list_updated_issues(
            since=watermark, limit=DEFAULT_SYNC_LIMIT
        )
        return [_record_to_event(source_type, record) for record in records]

    async def backfill_events(
        self,
        source_type: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[ConnectorEvent]:
        records = await self._provider.list_project_issues(
            since=since, limit=limit or DEFAULT_BACKFILL_LIMIT
        )
        return [_record_to_event(source_type, record) for record in records]


class GitHubReadOnlyConnectorClient:
    """Adapts a :class:`GitHubReadOnlyProvider` to the connector contract."""

    def __init__(self, provider: GitHubReadOnlyProvider) -> None:
        self._provider = provider

    async def test_connection(self, source_type: str) -> dict[str, Any]:
        return sanitize_for_logs(await self._provider.test_connection())

    async def sync_events(
        self, source_type: str, *, watermark: str | None = None
    ) -> list[ConnectorEvent]:
        records = await self._provider.list_repo_activity(
            since=watermark, limit=DEFAULT_SYNC_LIMIT
        )
        return [_record_to_event(source_type, record) for record in records]

    async def backfill_events(
        self,
        source_type: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[ConnectorEvent]:
        safe_limit = limit or DEFAULT_BACKFILL_LIMIT
        records = [
            *await self._provider.list_pull_requests(since=since, limit=safe_limit),
            *await self._provider.list_commits(since=since, limit=safe_limit),
        ]
        return [_record_to_event(source_type, record) for record in records]


class EmailReadOnlyConnectorClient:
    """Adapts an :class:`EmailReadOnlyProvider` to the connector contract."""

    def __init__(self, provider: EmailReadOnlyProvider) -> None:
        self._provider = provider

    async def test_connection(self, source_type: str) -> dict[str, Any]:
        return sanitize_for_logs(await self._provider.test_connection())

    async def sync_events(
        self, source_type: str, *, watermark: str | None = None
    ) -> list[ConnectorEvent]:
        records = await self._provider.list_threads(
            since=watermark, limit=DEFAULT_SYNC_LIMIT
        )
        return [_record_to_event(source_type, record) for record in records]

    async def backfill_events(
        self,
        source_type: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[ConnectorEvent]:
        records = await self._provider.list_threads(
            since=since, limit=limit or DEFAULT_BACKFILL_LIMIT
        )
        return [_record_to_event(source_type, record) for record in records]


# --- Live (real) provider boundary: no network until explicitly enabled ---


class _LiveProviderBase:
    """Shared refusal behavior for live providers.

    A live provider never performs a network call from this module. Live
    access is a future, explicitly-gated step (provider execution guard +
    operator ack); until then every method fails closed with a sanitized
    reason code instead of reaching an external API.
    """

    source_type = "external"

    def __init__(self, *, enabled: bool = False) -> None:
        self._enabled = enabled

    def _guard(self) -> None:
        if not self._enabled:
            raise ConnectorClientNotEnabledError(
                f"{self.source_type}_live_connector_disabled"
            )

    async def test_connection(self) -> dict[str, Any]:
        self._guard()
        raise ConnectorClientNotEnabledError(
            f"{self.source_type}_live_connector_disabled"
        )


class LiveJiraReadOnlyProvider(_LiveProviderBase):
    source_type = "jira"

    async def list_updated_issues(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        raise ConnectorClientNotEnabledError("jira_live_connector_disabled")

    async def list_project_issues(
        self,
        *,
        project: str | None = None,
        since: str | None = None,
        limit: int = DEFAULT_BACKFILL_LIMIT,
    ) -> list[ReadOnlyRecord]:
        self._guard()
        raise ConnectorClientNotEnabledError("jira_live_connector_disabled")


class LiveGitHubReadOnlyProvider(_LiveProviderBase):
    source_type = "github"

    async def list_repo_activity(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        raise ConnectorClientNotEnabledError("github_live_connector_disabled")

    async def list_pull_requests(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        raise ConnectorClientNotEnabledError("github_live_connector_disabled")

    async def list_commits(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        raise ConnectorClientNotEnabledError("github_live_connector_disabled")


class LiveEmailReadOnlyProvider(_LiveProviderBase):
    source_type = "gmail"

    async def list_threads(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        raise ConnectorClientNotEnabledError("gmail_live_connector_disabled")


def live_connector_clients() -> dict[str, ReadOnlyConnectorClient]:
    """Build the live read-only clients.

    These are *not* wired into the default registry; live access stays disabled
    until a future explicit enablement step. Returned here so the architecture
    is ready and so diagnostics can report adapter type ``real`` when wired.
    """

    return {
        "jira": JiraReadOnlyConnectorClient(LiveJiraReadOnlyProvider()),
        "github": GitHubReadOnlyConnectorClient(LiveGitHubReadOnlyProvider()),
        "gmail": EmailReadOnlyConnectorClient(LiveEmailReadOnlyProvider()),
    }
