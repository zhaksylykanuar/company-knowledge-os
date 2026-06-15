"""Read-only Jira discovery: GET-only metadata + issue summaries.

Builds a factual picture of an existing (messy) Jira instance to inform the
clean target model (`docs/ops/jira-target-blueprint.md`). Hard rules baked in:

- **GET only.** The transport contract is ``(method, path, params) -> json`` and
  the real transport refuses any method other than ``GET``. There is no write
  path in this module.
- **No bodies.** Issue search requests a restricted field set — never
  ``description``/``comment`` bodies — so free text is limited to issue titles.
- **Secret-scrubbed saves.** Anything written locally is run through
  :func:`app.services.secret_patterns` redaction first.
- **Bounded.** Pagination is capped; nothing fans out unboundedly.

Full data is written to local files by the caller; only sanitized counts and
classes are surfaced to stdout/chat.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.secret_patterns import contains_secret_value

GET = "GET"

# Restricted issue fields — structured only, never description/comment bodies.
ISSUE_FIELDS = (
    "summary,status,issuetype,assignee,priority,created,updated,"
    "resolutiondate,components,labels,project,parent"
)

# /search/jql rejects unbounded JQL; a wide date floor bounds it while still
# matching essentially every issue.
DEFAULT_ISSUE_JQL = 'created >= "2000-01-01" ORDER BY updated DESC'

# Endpoint labels (used as artifact names and per-endpoint status keys).
EP_PROJECTS = "projects"
EP_BOARDS = "boards"
EP_ISSUE_TYPES = "issue_types"
EP_FIELDS = "fields"
EP_STATUSES = "statuses"
EP_WORKFLOWS = "workflows"
EP_LABELS = "labels"
EP_COMPONENTS = "components"
EP_PERMISSIONS = "permissions"
EP_ISSUES = "issues"

ENDPOINT_LABELS = (
    EP_PROJECTS,
    EP_BOARDS,
    EP_ISSUE_TYPES,
    EP_FIELDS,
    EP_STATUSES,
    EP_WORKFLOWS,
    EP_LABELS,
    EP_COMPONENTS,
    EP_PERMISSIONS,
    EP_ISSUES,
)

FETCH_OK = "ok"
FETCH_FAILED = "fetch_failed"
FETCH_FORBIDDEN = "forbidden_or_unavailable"

# Target model reference (from the blueprint) for "mess" indicators.
TARGET_STATUS_COUNT = 8
TARGET_ISSUE_TYPE_COUNT = 8
STALE_ISSUE_DAYS = 30
REDACTED = "<redacted-secret>"

# Statuses we treat as terminal when computing stale/open work.
_DONE_STATUS_HINTS = ("done", "closed", "resolved", "released", "cancelled", "canceled")

JiraTransport = Callable[[str, str, Mapping[str, Any]], Any]


class JiraDiscoveryTransportError(RuntimeError):
    """Raised by a real transport if a non-GET method is ever attempted."""


@dataclass
class JiraDiscoveryRaw:
    """Collected read-only discovery data plus a per-endpoint status map."""

    endpoint_status: dict[str, str] = field(default_factory=dict)
    projects: list[dict[str, Any]] = field(default_factory=list)
    boards: list[dict[str, Any]] = field(default_factory=list)
    issue_types: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    statuses: list[dict[str, Any]] = field(default_factory=list)
    workflows: list[dict[str, Any]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    components: list[dict[str, Any]] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)


class JiraReadOnlyDiscoveryClient:
    """GET-only Jira REST client for discovery.

    ``transport`` is a callable ``(method, path, params) -> parsed_json``. This
    client only ever passes ``GET``; a real transport must reject anything else.
    """

    def __init__(self, transport: JiraTransport, *, page_cap: int = 20, page_size: int = 100):
        self._transport = transport
        self._page_cap = max(1, int(page_cap))
        self._page_size = max(1, min(int(page_size), 100))

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._transport(GET, path, dict(params or {}))

    def _get_values_paginated(self, path: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Page through a ``{values, isLast, startAt, maxResults}`` endpoint."""
        out: list[dict[str, Any]] = []
        start_at = 0
        for _ in range(self._page_cap):
            page = self._get(path, {**params, "startAt": start_at, "maxResults": self._page_size})
            if not isinstance(page, Mapping):
                break
            values = page.get("values")
            if isinstance(values, list):
                out.extend(item for item in values if isinstance(item, dict))
            if page.get("isLast") is True:
                break
            fetched = len(values) if isinstance(values, list) else 0
            # A short page is the last page (real Jira returns < maxResults then).
            if fetched < self._page_size:
                break
            start_at += fetched
        return out

    def projects(self) -> list[dict[str, Any]]:
        return self._get_values_paginated(
            "/rest/api/3/project/search", {"expand": "lead,description,insight"}
        )

    def boards(self) -> list[dict[str, Any]]:
        return self._get_values_paginated("/rest/agile/1.0/board", {})

    def issue_types(self) -> list[dict[str, Any]]:
        data = self._get("/rest/api/3/issuetype")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def fields(self) -> list[dict[str, Any]]:
        data = self._get("/rest/api/3/field")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def statuses(self) -> list[dict[str, Any]]:
        data = self._get("/rest/api/3/status")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def workflows(self) -> list[dict[str, Any]]:
        return self._get_values_paginated("/rest/api/3/workflow/search", {})

    def labels(self) -> list[str]:
        # /rest/api/3/label returns plain strings under "values", not dicts.
        out: list[str] = []
        start_at = 0
        for _ in range(self._page_cap):
            page = self._get(
                "/rest/api/3/label", {"startAt": start_at, "maxResults": self._page_size}
            )
            if not isinstance(page, Mapping):
                break
            values = page.get("values")
            chunk = [v for v in values if isinstance(v, str)] if isinstance(values, list) else []
            out.extend(chunk)
            if page.get("isLast") is True or not chunk:
                break
            start_at += len(chunk)
        return out

    def project_components(self, project_key: str) -> list[dict[str, Any]]:
        safe_key = "".join(c for c in str(project_key) if c.isalnum() or c == "_")
        if not safe_key:
            return []
        data = self._get(f"/rest/api/3/project/{safe_key}/components")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def permissions(self) -> dict[str, Any]:
        data = self._get(
            "/rest/api/3/mypermissions", {"permissions": "BROWSE_PROJECTS,ADMINISTER,CREATE_ISSUES"}
        )
        return dict(data) if isinstance(data, Mapping) else {}

    def search_issues(self, *, max_total: int = 500) -> list[dict[str, Any]]:
        # Jira Cloud removed the old GET /search (410). The enhanced endpoint
        # /search/jql rejects unbounded JQL, so a date restriction is required;
        # it also paginates by nextPageToken rather than startAt.
        out: list[dict[str, Any]] = []
        next_token: str | None = None
        for _ in range(self._page_cap):
            params: dict[str, Any] = {
                "jql": DEFAULT_ISSUE_JQL,
                "fields": ISSUE_FIELDS,
                "maxResults": self._page_size,
            }
            if next_token:
                params["nextPageToken"] = next_token
            page = self._get("/rest/api/3/search/jql", params)
            if not isinstance(page, Mapping):
                break
            issues = page.get("issues")
            chunk = [i for i in issues if isinstance(i, dict)] if isinstance(issues, list) else []
            out.extend(chunk)
            next_token = page.get("nextPageToken")
            if not chunk or not next_token or len(out) >= max_total:
                break
        return out[:max_total]


def collect_jira_discovery(client: JiraReadOnlyDiscoveryClient) -> JiraDiscoveryRaw:
    """Run every read-only fetch, isolating per-endpoint failures.

    A forbidden/unavailable endpoint (e.g. workflow search without admin) is
    recorded as a status and skipped; it never aborts the whole discovery.
    """
    raw = JiraDiscoveryRaw()

    raw.projects = _safe_fetch(raw, EP_PROJECTS, client.projects)
    raw.boards = _safe_fetch(raw, EP_BOARDS, client.boards)
    raw.issue_types = _safe_fetch(raw, EP_ISSUE_TYPES, client.issue_types)
    raw.fields = _safe_fetch(raw, EP_FIELDS, client.fields)
    raw.statuses = _safe_fetch(raw, EP_STATUSES, client.statuses)
    raw.workflows = _safe_fetch(raw, EP_WORKFLOWS, client.workflows)
    raw.labels = _safe_fetch(raw, EP_LABELS, client.labels)
    raw.issues = _safe_fetch(raw, EP_ISSUES, client.search_issues)

    permissions = _safe_fetch(raw, EP_PERMISSIONS, client.permissions, default={})
    raw.permissions = permissions if isinstance(permissions, dict) else {}

    # Components are per-project; collect across the discovered projects.
    components: list[dict[str, Any]] = []
    if raw.endpoint_status.get(EP_PROJECTS) == FETCH_OK:
        try:
            for project in raw.projects:
                key = project.get("key") if isinstance(project, dict) else None
                if not key:
                    continue
                for component in client.project_components(str(key)):
                    component.setdefault("_project_key", key)
                    components.append(component)
            raw.endpoint_status[EP_COMPONENTS] = FETCH_OK
        except Exception:
            raw.endpoint_status[EP_COMPONENTS] = FETCH_FORBIDDEN
    else:
        raw.endpoint_status[EP_COMPONENTS] = FETCH_FAILED
    raw.components = components
    return raw


def _safe_fetch(
    raw: JiraDiscoveryRaw, label: str, fetch: Callable[[], Any], *, default: Any = None
):
    try:
        result = fetch()
        raw.endpoint_status[label] = FETCH_OK
        return result
    except Exception:
        raw.endpoint_status[label] = FETCH_FORBIDDEN
        return [] if default is None else default


def summarize_jira_discovery(raw: JiraDiscoveryRaw) -> dict[str, Any]:
    """Produce a sanitized, counts-and-classes summary (safe for stdout)."""
    custom_fields = [f for f in raw.fields if isinstance(f, dict) and f.get("custom") is True]
    subtask_types = [t for t in raw.issue_types if isinstance(t, dict) and t.get("subtask") is True]

    status_names = _names(raw.statuses)
    issue_type_names = _names(raw.issue_types)

    status_distribution = _issue_field_distribution(raw.issues, ("status", "name"))
    type_distribution = _issue_field_distribution(raw.issues, ("issuetype", "name"))
    project_usage = _issue_field_distribution(raw.issues, ("project", "key"))
    stale_count = _stale_issue_count(raw.issues)
    unassigned_count = sum(1 for issue in raw.issues if not _nested(issue, ("fields", "assignee")))

    mess = _mess_indicators(
        status_names=status_names,
        issue_type_names=issue_type_names,
        custom_field_count=len(custom_fields),
        board_count=len(raw.boards),
        project_count=len(raw.projects),
    )

    return {
        "report_kind": "jira_discovery_summary",
        "endpoint_status": dict(raw.endpoint_status),
        "counts": {
            "project_count": len(raw.projects),
            "board_count": len(raw.boards),
            "issue_type_count": len(raw.issue_types),
            "subtask_issue_type_count": len(subtask_types),
            "status_count": len(raw.statuses),
            "field_count": len(raw.fields),
            "custom_field_count": len(custom_fields),
            "label_count": len(raw.labels),
            "component_count": len(raw.components),
            "issue_sample_count": len(raw.issues),
        },
        "issue_summary": {
            "status_distribution": status_distribution,
            "type_distribution": type_distribution,
            "project_usage": project_usage,
            "stale_issue_count": stale_count,
            "stale_threshold_days": STALE_ISSUE_DAYS,
            "unassigned_issue_count": unassigned_count,
        },
        "mess_indicators": mess,
    }


def _mess_indicators(
    *,
    status_names: Sequence[str],
    issue_type_names: Sequence[str],
    custom_field_count: int,
    board_count: int,
    project_count: int,
) -> dict[str, Any]:
    near_dupe_statuses = _near_duplicates(status_names)
    return {
        "status_proliferation": len(status_names) > TARGET_STATUS_COUNT,
        "status_over_target": max(0, len(status_names) - TARGET_STATUS_COUNT),
        "near_duplicate_status_count": len(near_dupe_statuses),
        "issue_type_proliferation": len(issue_type_names) > TARGET_ISSUE_TYPE_COUNT,
        "issue_type_over_target": max(0, len(issue_type_names) - TARGET_ISSUE_TYPE_COUNT),
        "custom_field_heavy": custom_field_count > 25,
        "boards_exceed_projects": board_count > max(1, project_count),
    }


def render_current_jira_audit(summary: Mapping[str, Any]) -> str:
    """Render the local current-jira-audit.md (founder-facing, no raw bodies)."""
    counts = summary.get("counts", {})
    issue = summary.get("issue_summary", {})
    mess = summary.get("mess_indicators", {})
    status_dist = issue.get("status_distribution", {})
    type_dist = issue.get("type_distribution", {})

    lines = [
        "# Current Jira Audit (read-only discovery)",
        "",
        "Generated by `scripts/run_jira_discovery.py`. Read-only, GET-only, no",
        "issue bodies fetched. Legacy/reference only — input for the clean target",
        "model in `docs/ops/jira-target-blueprint.md`.",
        "",
        "## Inventory counts",
        "",
        f"- Projects: {counts.get('project_count', 0)}",
        f"- Boards: {counts.get('board_count', 0)}",
        f"- Issue types: {counts.get('issue_type_count', 0)} "
        f"({counts.get('subtask_issue_type_count', 0)} subtask types)",
        f"- Statuses: {counts.get('status_count', 0)}",
        f"- Fields: {counts.get('field_count', 0)} ({counts.get('custom_field_count', 0)} custom)",
        f"- Labels: {counts.get('label_count', 0)}",
        f"- Components: {counts.get('component_count', 0)}",
        f"- Issue sample analyzed: {counts.get('issue_sample_count', 0)}",
        "",
        "## Issue distribution (sample)",
        "",
        "By status:",
        *(f"- {name}: {count}" for name, count in _top(status_dist)),
        "",
        "By type:",
        *(f"- {name}: {count}" for name, count in _top(type_dist)),
        "",
        f"- Stale (> {issue.get('stale_threshold_days', STALE_ISSUE_DAYS)}d, not done): "
        f"{issue.get('stale_issue_count', 0)}",
        f"- Unassigned: {issue.get('unassigned_issue_count', 0)}",
        "",
        "## Mess indicators (vs target model)",
        "",
        f"- Status proliferation: {mess.get('status_proliferation', False)} "
        f"(+{mess.get('status_over_target', 0)} over target {TARGET_STATUS_COUNT})",
        f"- Near-duplicate statuses: {mess.get('near_duplicate_status_count', 0)}",
        f"- Issue type proliferation: {mess.get('issue_type_proliferation', False)} "
        f"(+{mess.get('issue_type_over_target', 0)} over target {TARGET_ISSUE_TYPE_COUNT})",
        f"- Custom-field heavy: {mess.get('custom_field_heavy', False)}",
        f"- Boards exceed projects: {mess.get('boards_exceed_projects', False)}",
        "",
        "## Endpoint access",
        "",
        *(
            f"- {label}: {summary.get('endpoint_status', {}).get(label, 'not_run')}"
            for label in ENDPOINT_LABELS
        ),
        "",
        "All raw responses are in the sibling `raw/` directory (local only).",
        "",
    ]
    return "\n".join(lines)


def scrub_for_save(value: Any) -> Any:
    """Recursively replace any secret-bearing string with a redaction marker.

    Defense in depth before writing raw discovery data locally: issue titles or
    field values that accidentally contain a token/key are neutralized.
    """
    if isinstance(value, str):
        return REDACTED if contains_secret_value(value) else value
    if isinstance(value, Mapping):
        return {key: scrub_for_save(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_for_save(item) for item in value]
    return value


# --- helpers -------------------------------------------------------------
def _names(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(r.get("name", "")) for r in records if isinstance(r, Mapping) and r.get("name")]


def _nested(record: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = record
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _issue_field_distribution(
    issues: Sequence[Mapping[str, Any]], nested_path: Sequence[str]
) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for issue in issues:
        fields = issue.get("fields") if isinstance(issue, Mapping) else None
        if not isinstance(fields, Mapping):
            continue
        value = _nested(fields, nested_path)
        if isinstance(value, str) and value:
            distribution[value] = distribution.get(value, 0) + 1
    return dict(sorted(distribution.items(), key=lambda kv: (-kv[1], kv[0])))


def _stale_issue_count(issues: Sequence[Mapping[str, Any]]) -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    count = 0
    for issue in issues:
        fields = issue.get("fields") if isinstance(issue, Mapping) else None
        if not isinstance(fields, Mapping):
            continue
        status_name = str(_nested(fields, ("status", "name")) or "").casefold()
        if any(hint in status_name for hint in _DONE_STATUS_HINTS):
            continue
        updated = _parse_iso(fields.get("updated"))
        if updated is not None and (now - updated).days > STALE_ISSUE_DAYS:
            count += 1
    return count


def _parse_iso(value: Any):
    from datetime import datetime

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    # Jira uses e.g. 2026-01-02T03:04:05.000+0000 — normalize the offset colon.
    if len(text) >= 5 and (text[-5] in "+-") and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _near_duplicates(names: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    for name in names:
        key = name.strip().casefold().replace(" ", "").replace("-", "").replace("_", "")
        seen[key] = seen.get(key, 0) + 1
    return [key for key, count in seen.items() if count > 1]


def _top(distribution: Mapping[str, int], limit: int = 15) -> list[tuple[str, int]]:
    return list(distribution.items())[:limit]
