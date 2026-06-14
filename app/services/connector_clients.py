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

import base64
import os
import re
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


# --- Real (live) read-only providers: gated, read-only HTTP --------------
#
# These perform real HTTP GET requests ONLY when real connectors are enabled.
# When disabled they fail closed (no network) with a sanitized reason code.
# All requests are read-only; no method ever writes to an external system.
# The pure mapping helpers (``map_*``) are unit-tested with sample API payloads
# so the risky parsing is covered without any network access.


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    match = re.match(
        r"^(.*[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)([+-]\d{2})(\d{2})$", text
    )
    if match:
        try:
            return datetime.fromisoformat(
                f"{match.group(1)}{match.group(2)}:{match.group(3)}"
            )
        except ValueError:
            return None
    return None


def _first_line(value: Any, *, limit: int = 200) -> str:
    text = str(value or "")
    line = text.splitlines()[0] if text.splitlines() else text
    return line[:limit]


def map_jira_issue(raw: dict[str, Any], *, base_url: str) -> ReadOnlyRecord:
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    key = str(raw.get("key") or raw.get("id") or "")
    status = (fields.get("status") or {}).get("name") if isinstance(fields.get("status"), dict) else None
    assignee = (
        (fields.get("assignee") or {}).get("displayName")
        if isinstance(fields.get("assignee"), dict)
        else None
    )
    project = (
        (fields.get("project") or {}).get("key")
        if isinstance(fields.get("project"), dict)
        else None
    )
    summary_bits = [bit for bit in (f"status={status}" if status else None,) if bit]
    browse = f"{base_url.rstrip('/')}/browse/{key}" if base_url and key else None
    return ReadOnlyRecord(
        external_id=key or "unknown",
        object_type="issue",
        event_type="jira.issue.updated",
        occurred_at=_parse_iso(fields.get("updated")),
        title=str(fields.get("summary") or key or "Jira issue"),
        summary="; ".join(summary_bits) or None,
        actor=assignee,
        url=browse,
        metadata={
            "project": project,
            "status": status,
            "issue_key": key,
        },
    )


def map_github_pull_request(raw: dict[str, Any], *, repo: str) -> ReadOnlyRecord:
    number = raw.get("number")
    user = (raw.get("user") or {}).get("login") if isinstance(raw.get("user"), dict) else None
    return ReadOnlyRecord(
        external_id=f"{repo}#pull/{number}",
        object_type="pull_request",
        event_type="github.pull_request.updated",
        occurred_at=_parse_iso(raw.get("updated_at")),
        title=str(raw.get("title") or f"PR #{number}"),
        summary=f"state={raw.get('state')}" if raw.get("state") else None,
        actor=user,
        url=raw.get("html_url"),
        metadata={"repo": repo, "number": number, "state": raw.get("state")},
    )


def map_github_issue(raw: dict[str, Any], *, repo: str) -> ReadOnlyRecord:
    number = raw.get("number")
    user = (raw.get("user") or {}).get("login") if isinstance(raw.get("user"), dict) else None
    return ReadOnlyRecord(
        external_id=f"{repo}#issue/{number}",
        object_type="issue",
        event_type="github.issue.updated",
        occurred_at=_parse_iso(raw.get("updated_at")),
        title=str(raw.get("title") or f"Issue #{number}"),
        summary=f"state={raw.get('state')}" if raw.get("state") else None,
        actor=user,
        url=raw.get("html_url"),
        metadata={"repo": repo, "number": number, "state": raw.get("state")},
    )


def map_github_commit(raw: dict[str, Any], *, repo: str) -> ReadOnlyRecord:
    sha = str(raw.get("sha") or "")
    commit = raw.get("commit") if isinstance(raw.get("commit"), dict) else {}
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    return ReadOnlyRecord(
        external_id=f"{repo}@{sha}",
        object_type="commit",
        event_type="github.commit.recorded",
        occurred_at=_parse_iso(author.get("date")),
        title=_first_line(commit.get("message") or sha),
        actor=author.get("name"),
        url=raw.get("html_url"),
        metadata={"repo": repo, "sha": sha},
    )


class _RealProviderBase:
    """Shared gating for real providers.

    ``_guard`` fails closed (no network) when real connectors are disabled or
    required config is missing. ``ConnectorClientNotEnabledError`` carries a
    sanitized reason code only.
    """

    source_type = "external"

    def __init__(self, *, enabled: bool = False, timeout: float = 10.0) -> None:
        self._enabled = enabled
        self._timeout = timeout

    def _has_config(self) -> bool:
        return True

    def _guard(self) -> None:
        if not self._enabled:
            raise ConnectorClientNotEnabledError(
                f"{self.source_type}_real_connector_disabled"
            )
        if not self._has_config():
            raise ConnectorClientNotEnabledError(
                f"{self.source_type}_missing_config"
            )


class LiveJiraReadOnlyProvider(_RealProviderBase):
    source_type = "jira"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        enabled: bool = False,
        timeout: float = 10.0,
        sync_limit: int = DEFAULT_SYNC_LIMIT,
        backfill_limit: int = DEFAULT_BACKFILL_LIMIT,
    ) -> None:
        super().__init__(enabled=enabled, timeout=timeout)
        self._base_url = (base_url or "").strip()
        self._email = (email or "").strip()
        self._token = token or ""
        self._sync_limit = sync_limit
        self._backfill_limit = backfill_limit

    def _has_config(self) -> bool:
        return bool(self._base_url and self._email and self._token)

    def _headers(self) -> dict[str, str]:
        raw = f"{self._email}:{self._token}".encode("utf-8")
        return {
            "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            "Accept": "application/json",
        }

    async def test_connection(self) -> dict[str, Any]:
        self._guard()
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url.rstrip('/')}/rest/api/3/myself",
                headers=self._headers(),
            )
            resp.raise_for_status()
        return {"status": "ok", "checked": "jira", "real_execution": "enabled"}

    async def _search(self, *, jql: str, limit: int) -> list[ReadOnlyRecord]:
        self._guard()
        import httpx

        params = {
            "jql": jql,
            "maxResults": max(1, int(limit)),
            "fields": "summary,status,assignee,updated,project",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url.rstrip('/')}/rest/api/3/search",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        issues = data.get("issues") if isinstance(data, dict) else None
        return [
            map_jira_issue(issue, base_url=self._base_url)
            for issue in (issues or [])
            if isinstance(issue, dict)
        ]

    async def list_updated_issues(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        return await self._search(
            jql=_jira_updated_jql(since), limit=min(limit, self._sync_limit)
        )

    async def list_project_issues(
        self,
        *,
        project: str | None = None,
        since: str | None = None,
        limit: int = DEFAULT_BACKFILL_LIMIT,
    ) -> list[ReadOnlyRecord]:
        return await self._search(
            jql=_jira_updated_jql(since), limit=min(limit, self._backfill_limit)
        )


def _jira_updated_jql(since: str | None) -> str:
    # Only accept an ISO-ish date prefix from our own watermark; never inject
    # arbitrary text into JQL.
    if isinstance(since, str) and re.match(r"^\d{4}-\d{2}-\d{2}", since.strip()):
        day = since.strip()[:10]
        return f'updated >= "{day}" ORDER BY updated DESC'
    return "ORDER BY updated DESC"


class LiveGitHubReadOnlyProvider(_RealProviderBase):
    source_type = "github"

    def __init__(
        self,
        *,
        token: str | None = None,
        repos: tuple[str, ...] = (),
        enabled: bool = False,
        timeout: float = 10.0,
        sync_limit: int = DEFAULT_SYNC_LIMIT,
        backfill_limit: int = DEFAULT_BACKFILL_LIMIT,
    ) -> None:
        super().__init__(enabled=enabled, timeout=timeout)
        self._token = token or ""
        self._repos = tuple(repo for repo in repos if repo)
        self._sync_limit = sync_limit
        self._backfill_limit = backfill_limit

    def _has_config(self) -> bool:
        return bool(self._token and self._repos)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }

    async def _get(self, url: str, params: dict[str, Any]):
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()

    async def test_connection(self) -> dict[str, Any]:
        self._guard()
        await self._get("https://api.github.com/user", {})
        return {"status": "ok", "checked": "github", "real_execution": "enabled"}

    async def list_pull_requests(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        records: list[ReadOnlyRecord] = []
        for repo in self._repos:
            data = await self._get(
                f"https://api.github.com/repos/{repo}/pulls",
                {"state": "all", "per_page": max(1, int(limit)), "sort": "updated", "direction": "desc"},
            )
            records.extend(
                map_github_pull_request(item, repo=repo)
                for item in (data or [])
                if isinstance(item, dict)
            )
        return records

    async def list_commits(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        records: list[ReadOnlyRecord] = []
        for repo in self._repos:
            params: dict[str, Any] = {"per_page": max(1, int(limit))}
            if isinstance(since, str) and since.strip():
                params["since"] = since.strip()
            data = await self._get(
                f"https://api.github.com/repos/{repo}/commits", params
            )
            records.extend(
                map_github_commit(item, repo=repo)
                for item in (data or [])
                if isinstance(item, dict)
            )
        return records

    async def list_repo_activity(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        self._guard()
        records: list[ReadOnlyRecord] = []
        for repo in self._repos:
            data = await self._get(
                f"https://api.github.com/repos/{repo}/issues",
                {"state": "all", "per_page": max(1, int(limit)), "sort": "updated", "direction": "desc"},
            )
            for item in data or []:
                if not isinstance(item, dict):
                    continue
                if item.get("pull_request"):
                    records.append(map_github_pull_request(item, repo=repo))
                else:
                    records.append(map_github_issue(item, repo=repo))
        return records


class LiveEmailReadOnlyProvider(_RealProviderBase):
    """Gmail real provider is not implemented in Stage 15 (local-only).

    It always fails closed; email diagnostics stay ``local_only`` /
    ``oauth_not_configured`` rather than fake-connected.
    """

    source_type = "gmail"

    async def test_connection(self) -> dict[str, Any]:
        raise ConnectorClientNotEnabledError("gmail_oauth_not_configured")

    async def list_threads(
        self, *, since: str | None = None, limit: int = DEFAULT_SYNC_LIMIT
    ) -> list[ReadOnlyRecord]:
        raise ConnectorClientNotEnabledError("gmail_oauth_not_configured")


def _env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_real_connector_clients(
    config: Any = None,
) -> dict[str, ReadOnlyConnectorClient]:
    """Build real read-only clients for Jira and GitHub from config/env.

    Providers self-gate on ``enable_real_connectors``; when disabled they never
    touch the network. Gmail is intentionally excluded (local-only in Stage 15).
    """

    from app.core.config import settings as default_settings

    cfg = config if config is not None else default_settings
    enabled = bool(getattr(cfg, "enable_real_connectors", False))
    timeout = float(getattr(cfg, "connector_network_timeout_seconds", 10) or 10)
    sync_limit = int(getattr(cfg, "connector_sync_limit", DEFAULT_SYNC_LIMIT) or DEFAULT_SYNC_LIMIT)
    backfill_limit = int(
        getattr(cfg, "connector_backfill_limit", DEFAULT_BACKFILL_LIMIT)
        or DEFAULT_BACKFILL_LIMIT
    )

    jira = LiveJiraReadOnlyProvider(
        base_url=(getattr(cfg, "jira_base_url", None) or _env("JIRA_BASE_URL")),
        email=(getattr(cfg, "jira_email", None) or _env("JIRA_EMAIL")),
        token=(getattr(cfg, "jira_api_token", None) or _env("JIRA_API_TOKEN")),
        enabled=enabled,
        timeout=timeout,
        sync_limit=sync_limit,
        backfill_limit=backfill_limit,
    )
    repos = _env("GITHUB_REPOS")
    repo_tuple = tuple(part.strip() for part in repos.split(",") if part.strip()) if repos else ()
    github = LiveGitHubReadOnlyProvider(
        token=_env("GITHUB_TOKEN", "FOS_GITHUB_READONLY_TOKEN"),
        repos=repo_tuple,
        enabled=enabled,
        timeout=timeout,
        sync_limit=sync_limit,
        backfill_limit=backfill_limit,
    )
    return {
        "jira": JiraReadOnlyConnectorClient(jira),
        "github": GitHubReadOnlyConnectorClient(github),
    }


def live_connector_clients() -> dict[str, ReadOnlyConnectorClient]:
    """Disabled-by-default live clients (boundary ready, no network).

    Returns providers constructed with no config and ``enabled=False`` so every
    call fails closed. The orchestrator wires configured real clients only when
    ``FOUNDEROS_ENABLE_REAL_CONNECTORS`` is true (see
    ``build_real_connector_clients``).
    """

    return {
        "jira": JiraReadOnlyConnectorClient(LiveJiraReadOnlyProvider()),
        "github": GitHubReadOnlyConnectorClient(LiveGitHubReadOnlyProvider()),
        "gmail": EmailReadOnlyConnectorClient(LiveEmailReadOnlyProvider()),
    }
