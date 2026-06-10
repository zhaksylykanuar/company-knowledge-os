from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from typing import Any

from app.services.attention_triage import NormalizedActivityItem

MAX_SAFE_SUMMARY_CHARS = 1200
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class SourceActivityMappingError(ValueError):
    pass


@dataclass(frozen=True)
class GitHubPullRequestActivityInput:
    source_object_id: str
    event_type: str
    title: str | None = None
    summary: str | None = None
    source_url: str | None = None
    actor: str | None = None
    repository_full_name: str | None = None
    pull_request_number: int | str | None = None
    assignees: Sequence[str] = field(default_factory=tuple)
    requested_reviewers: Sequence[str] = field(default_factory=tuple)
    requested_teams: Sequence[str] = field(default_factory=tuple)
    project: str | None = None
    created_at: datetime | None = None
    source_event_id: str | None = None
    raw_payload_ref: str | None = None


@dataclass(frozen=True)
class JiraIssueActivityInput:
    source_object_id: str
    event_type: str
    title: str | None = None
    summary: str | None = None
    source_url: str | None = None
    actor: str | None = None
    issue_key: str | None = None
    assignee: str | None = None
    project_key: str | None = None
    status: str | None = None
    labels: Sequence[str] = field(default_factory=tuple)
    blocked: bool = False
    blocked_reason: str | None = None
    project: str | None = None
    created_at: datetime | None = None
    source_event_id: str | None = None
    raw_payload_ref: str | None = None


@dataclass(frozen=True)
class DriveDocumentActivityInput:
    source_object_id: str
    event_type: str
    title: str | None = None
    name: str | None = None
    summary: str | None = None
    source_url: str | None = None
    web_view_link: str | None = None
    actor: str | None = None
    source_document_id: str | None = None
    modified_at: datetime | None = None
    created_at: datetime | None = None
    project: str | None = None
    topic: str | None = None
    topics: Sequence[str] = field(default_factory=tuple)
    source_event_id: str | None = None
    raw_payload_ref: str | None = None


@dataclass(frozen=True)
class GmailMessageActivityInput:
    source_object_id: str
    event_type: str
    title: str | None = None
    subject: str | None = None
    summary: str | None = None
    source_url: str | None = None
    actor: str | None = None
    from_address: str | None = None
    created_at: datetime | None = None
    source_event_id: str | None = None
    raw_payload_ref: str | None = None


def github_pr_event_to_activity_item(
    event: GitHubPullRequestActivityInput | Mapping[str, Any] | Any,
) -> NormalizedActivityItem:
    data = _event_data(event)
    source_object_id = _required_string(data, "source_object_id")
    event_type = _clean_string(data.get("event_type")) or "github.pull_request.updated"
    title = _safe_text(_first(data, "title", "name"), max_chars=500)
    summary = _safe_text(data.get("summary"))
    source_url = _clean_string(data.get("source_url"))
    actor = _clean_string(_first(data, "actor", "actor_external_id"))
    repository = _clean_string(data.get("repository_full_name"))
    pull_request_number = _clean_string(data.get("pull_request_number"))
    assignees = _string_sequence(data.get("assignees"))
    requested_reviewers = _string_sequence(data.get("requested_reviewers"))
    requested_teams = _team_labels(_string_sequence(data.get("requested_teams")))

    related_prs = _unique_strings(
        [
            source_url,
            _pr_ref(repository=repository, pull_request_number=pull_request_number),
        ]
    )

    return NormalizedActivityItem(
        source="github",
        source_object_id=source_object_id,
        activity_type=_github_pr_activity_type(
            event_type=event_type,
            assignees=assignees,
            requested_reviewers=requested_reviewers,
            requested_teams=requested_teams,
        ),
        title=title,
        actor=actor,
        created_at=_first(data, "created_at", "event_time"),
        project=_clean_string(data.get("project")) or repository,
        safe_summary=summary,
        related_people=_unique_strings([actor, *assignees, *requested_reviewers, *requested_teams]),
        related_jira_keys=_extract_jira_keys(title, summary),
        related_prs=related_prs,
        related_files=[],
        evidence_refs=_evidence_refs(
            source="github",
            source_object_id=source_object_id,
            event_type=event_type,
            source_event_id=_clean_string(data.get("source_event_id")),
            raw_payload_ref=_clean_string(_first(data, "raw_payload_ref", "raw_object_ref")),
            source_url=source_url,
        ),
    )


def jira_issue_event_to_activity_item(
    event: JiraIssueActivityInput | Mapping[str, Any] | Any,
) -> NormalizedActivityItem:
    data = _event_data(event)
    source_object_id = _required_string(data, "source_object_id")
    event_type = _clean_string(data.get("event_type")) or "jira.issue.updated"
    title = _safe_text(_first(data, "title", "name"), max_chars=500)
    summary = _jira_safe_summary(data)
    source_url = _clean_string(data.get("source_url"))
    actor = _clean_string(_first(data, "actor", "actor_external_id"))
    issue_key = _clean_string(data.get("issue_key")) or _first_jira_key(source_object_id, title)
    assignee = _clean_string(data.get("assignee"))
    project_key = _clean_string(data.get("project_key"))
    labels = _string_sequence(data.get("labels"))
    related_jira_keys = _unique_strings([issue_key, *_extract_jira_keys(title, summary)])

    return NormalizedActivityItem(
        source="jira",
        source_object_id=source_object_id,
        activity_type=_jira_issue_activity_type(data),
        title=title,
        actor=actor,
        created_at=_first(data, "created_at", "event_time"),
        project=_clean_string(data.get("project")) or project_key,
        safe_summary=summary,
        related_people=_unique_strings([actor, assignee]),
        related_jira_keys=related_jira_keys,
        related_prs=_string_sequence(data.get("related_prs")),
        related_files=[],
        evidence_refs=_evidence_refs(
            source="jira",
            source_object_id=source_object_id,
            event_type=event_type,
            source_event_id=_clean_string(data.get("source_event_id")),
            raw_payload_ref=_clean_string(_first(data, "raw_payload_ref", "raw_object_ref")),
            source_url=source_url,
            extra={"issue_key": issue_key, "status": _clean_string(data.get("status")), "labels": labels},
        ),
    )


def drive_document_event_to_activity_item(
    event: DriveDocumentActivityInput | Mapping[str, Any] | Any,
) -> NormalizedActivityItem:
    data = _event_data(event)
    source_object_id = _required_string(data, "source_object_id")
    event_type = _clean_string(data.get("event_type")) or "drive.file.updated"
    title = _safe_text(_first(data, "title", "name"), max_chars=500)
    summary = _safe_text(data.get("summary"))
    source_url = _clean_string(_first(data, "source_url", "webViewLink", "web_view_link"))
    actor = _clean_string(_first(data, "actor", "actor_external_id"))
    source_document_id = _clean_string(
        _first(data, "source_document_id", "document_id", "drive_file_id")
    )
    topics = _string_sequence(data.get("topics"))
    project = _clean_string(data.get("project")) or _clean_string(data.get("topic"))

    return NormalizedActivityItem(
        source="drive",
        source_object_id=source_object_id,
        activity_type="document.changed",
        title=title,
        actor=actor,
        created_at=_first(data, "modified_at", "created_at", "event_time"),
        project=project,
        safe_summary=summary,
        related_people=_unique_strings([actor]),
        related_jira_keys=_extract_jira_keys(title, summary),
        related_prs=_string_sequence(data.get("related_prs")),
        related_files=_unique_strings([source_url, source_document_id]),
        evidence_refs=_evidence_refs(
            source="drive",
            source_object_id=source_object_id,
            event_type=event_type,
            source_event_id=_clean_string(data.get("source_event_id")),
            raw_payload_ref=_clean_string(_first(data, "raw_payload_ref", "raw_object_ref")),
            source_url=source_url,
            extra={
                "source_document_id": source_document_id,
                "topics": topics,
            },
        ),
    )


def gmail_message_event_to_activity_item(
    event: GmailMessageActivityInput | Mapping[str, Any] | Any,
) -> NormalizedActivityItem:
    data = _event_data(event)
    source_object_id = _required_string(data, "source_object_id")
    event_type = _clean_string(data.get("event_type")) or "gmail.message.ingested"
    title = _safe_text(_first(data, "title", "subject"), max_chars=500)
    summary = _safe_text(data.get("summary"))
    source_url = _clean_string(data.get("source_url"))
    actor = _clean_string(_first(data, "actor", "actor_external_id", "from_address"))

    return NormalizedActivityItem(
        source="gmail",
        source_object_id=source_object_id,
        activity_type="email.received",
        title=title,
        actor=actor,
        created_at=_first(data, "created_at", "event_time"),
        project=None,
        safe_summary=summary,
        related_people=_unique_strings([actor]),
        related_jira_keys=_extract_jira_keys(title, summary),
        related_prs=[],
        related_files=[],
        evidence_refs=_evidence_refs(
            source="gmail",
            source_object_id=source_object_id,
            event_type=event_type,
            source_event_id=_clean_string(data.get("source_event_id")),
            raw_payload_ref=_clean_string(_first(data, "raw_payload_ref", "raw_object_ref")),
            source_url=source_url,
        ),
    )


def source_event_to_activity_item(event: Mapping[str, Any] | Any) -> NormalizedActivityItem:
    data = _event_data(event)
    source = _clean_string(_first(data, "source", "source_system"))
    source_object_type = _clean_string(_first(data, "source_object_type", "object_type"))

    if source == "github" and source_object_type == "pull_request":
        return github_pr_event_to_activity_item(event)
    if source == "jira" and source_object_type == "issue":
        return jira_issue_event_to_activity_item(event)
    if source == "drive" and source_object_type in {"file", "document"}:
        return drive_document_event_to_activity_item(event)
    if source == "gmail" and source_object_type == "message":
        return gmail_message_event_to_activity_item(event)

    raise SourceActivityMappingError(
        f"unsupported source activity mapping: {source or 'unknown'}.{source_object_type or 'unknown'}"
    )


def _event_data(event: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(event, Mapping):
        data = dict(event)
    elif is_dataclass(event):
        data = asdict(event)
    else:
        data = {
            key: value
            for key in _KNOWN_INPUT_FIELDS
            if (value := getattr(event, key, None)) is not None
        }

    for nested_key in ("payload_subset", "payload"):
        nested = data.get(nested_key)
        if isinstance(nested, Mapping):
            for key, value in nested.items():
                data.setdefault(str(key), value)

    return data


_KNOWN_INPUT_FIELDS = {
    "actor",
    "actor_external_id",
    "assignee",
    "assignees",
    "blocked",
    "blocked_reason",
    "created_at",
    "document_id",
    "drive_file_id",
    "event_time",
    "event_type",
    "from_address",
    "issue_key",
    "labels",
    "metadata_json",
    "modified_at",
    "name",
    "object_type",
    "payload",
    "payload_subset",
    "project",
    "project_key",
    "pull_request_number",
    "raw_object_ref",
    "raw_payload_ref",
    "related_prs",
    "repository_full_name",
    "requested_reviewers",
    "requested_teams",
    "source",
    "source_document_id",
    "source_event_id",
    "source_object_id",
    "source_object_type",
    "source_system",
    "source_url",
    "status",
    "subject",
    "summary",
    "title",
    "topic",
    "topics",
    "webViewLink",
    "web_view_link",
}


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = _clean_string(data.get(key))
    if value is None:
        raise SourceActivityMappingError(f"{key} is required")
    return value


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _clean_string(value: Any) -> str | None:
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _safe_text(value: Any, *, max_chars: int = MAX_SAFE_SUMMARY_CHARS) -> str | None:
    cleaned = _clean_string(value)
    if cleaned is None:
        return None
    normalized = " ".join(cleaned.split())
    return normalized[:max_chars]


def _string_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str | int):
        cleaned = _clean_string(value)
        return [cleaned] if cleaned else []
    if not isinstance(value, Sequence):
        return []
    return _unique_strings(_clean_string(item) for item in value)


def _unique_strings(values: Sequence[str | None] | Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        cleaned = _clean_string(value)
        if cleaned is None or cleaned in seen:
            continue
        unique.append(cleaned)
        seen.add(cleaned)
    return unique


def _team_labels(teams: Sequence[str]) -> list[str]:
    return [f"team:{team}" for team in teams]


def _github_pr_activity_type(
    *,
    event_type: str,
    assignees: Sequence[str],
    requested_reviewers: Sequence[str],
    requested_teams: Sequence[str],
) -> str:
    event_type_lower = event_type.casefold()
    if requested_reviewers or requested_teams or "review" in event_type_lower:
        return "pull_request.review_requested"
    if assignees or "assigned" in event_type_lower:
        return "pull_request.assigned"
    return "pull_request.updated"


def _pr_ref(*, repository: str | None, pull_request_number: str | None) -> str | None:
    if repository and pull_request_number:
        return f"{repository}#{pull_request_number}"
    return None


def _jira_issue_activity_type(data: Mapping[str, Any]) -> str:
    event_type = (_clean_string(data.get("event_type")) or "").casefold()
    status = (_clean_string(data.get("status")) or "").casefold()
    blocked_reason = _clean_string(data.get("blocked_reason"))
    if _bool_value(data.get("blocked")) or blocked_reason or "blocked" in status:
        return "issue.blocked"
    if _clean_string(data.get("assignee")) or "assigned" in event_type:
        return "issue.assigned"
    return "issue.updated"


def _jira_safe_summary(data: Mapping[str, Any]) -> str | None:
    summary = _safe_text(data.get("summary"))
    blocked_reason = _safe_text(data.get("blocked_reason"), max_chars=300)
    if blocked_reason is None:
        return summary
    blocker_text = f"Blocker: {blocked_reason}"
    if summary is None:
        return blocker_text
    if blocked_reason in summary:
        return summary
    return _safe_text(f"{summary} {blocker_text}")


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return False


def _extract_jira_keys(*values: str | None) -> list[str]:
    matches: list[str] = []
    for value in values:
        if not value:
            continue
        matches.extend(_JIRA_KEY_RE.findall(value))
    return _unique_strings(matches)


def _first_jira_key(*values: str | None) -> str | None:
    keys = _extract_jira_keys(*values)
    return keys[0] if keys else None


def _evidence_refs(
    *,
    source: str,
    source_object_id: str,
    event_type: str,
    source_event_id: str | None,
    raw_payload_ref: str | None,
    source_url: str | None,
    extra: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ref: dict[str, Any] = {
        "kind": "source_activity",
        "source": source,
        "source_object_id": source_object_id,
        "event_type": event_type,
    }
    if source_event_id:
        ref["source_event_id"] = source_event_id
    if raw_payload_ref:
        ref["raw_payload_ref"] = raw_payload_ref
    if source_url:
        ref["source_url"] = source_url
    if extra:
        for key, value in extra.items():
            if isinstance(value, list):
                cleaned_values = _string_sequence(value)
                if cleaned_values:
                    ref[key] = cleaned_values
                continue
            cleaned = _clean_string(value)
            if cleaned:
                ref[key] = cleaned
    return [ref]
