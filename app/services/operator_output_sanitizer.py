from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

RAW_HASH_RE = re.compile(r"(?i)\b(?:sha256[:=_-]?)?[a-f0-9]{40,}\b")
URL_RE = re.compile(r"(?i)\b(?:https?|git|ssh|postgres(?:ql)?|mysql|redis|mongodb)://")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|bot[_-]?token|chat[_-]?id|credential|password|secret|token|webhook)\b"
)
RAW_PAYLOAD_RE = re.compile(
    r"(?i)\b(?:provider[_-]?payload|raw[_-]?payload|raw[_-]?source|source[_-]?payload|raw[_-]?body)\b"
)
DATABASE_RE = re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|redis|mongodb)://")

UNSAFE_JSON_FLAG_CLASSES = {
    "chunk_text_like": ("chunk_text",),
    "item_text_like": (
        "item_action",
        "item_summary",
        "item_title",
        "recommended_action",
        "safe_summary",
    ),
    "preview_text_like": ("grouped_preview", "grouped_preview_text"),
    "raw_guarded_execution_payload_like": (
        "raw_audit_json",
        "raw_config_doctor_json",
        "raw_contract_validation_payload",
        "raw_doctor_json",
        "raw_readiness_json",
        "raw_sink_contents",
        "raw_smoke_json",
    ),
    "rendered_text_like": ("rendered_digest_text", "rendered_text"),
    "source_identifier": (
        "author_email",
        "author_name",
        "evidence_refs",
        "remote_url",
        "repository_name",
        "source_id",
        "source_object_id",
    ),
}
SAFE_DIAGNOSTIC_CLASS_VALUES = frozenset(
    {
        "database_connection_like",
        "email_like_value",
        "payload_like_value",
        "raw_hash_shaped_value",
        "secret_rotation_required",
        "secret_like_value",
        "env_secret_file",
        "cache_directory",
        "python_cache",
        "node_modules",
        "build_output",
        "test_artifact",
        "temp_artifact",
        "log_file",
        "local_database",
        "raw_source_of_truth_store",
        "obsidian_vault_store",
        "unknown_ignored",
        "keep_local_secret",
        "safe_to_delete_candidate",
        "review_before_delete",
        "keep_cache",
        "ignore_rule_review",
        "source_of_truth_do_not_touch",
        "url_like_value",
        *UNSAFE_JSON_FLAG_CLASSES,
    }
)
SAFE_ENVIRONMENT_VARIABLE_NAMES = frozenset(
    {
        "FOS_GITHUB_READONLY_ACCOUNT",
        "FOS_GITHUB_READONLY_TOKEN",
        "FOS_JIRA_READONLY_SITE",
        "FOS_JIRA_READONLY_TOKEN",
        "FOS_JIRA_READONLY_USER",
        "FOS_GMAIL_READONLY_CLIENT_ID",
        "FOS_GMAIL_READONLY_CLIENT_SECRET",
        "FOS_GOOGLE_DRIVE_READONLY_CLIENT_ID",
        "FOS_GOOGLE_DRIVE_READONLY_CLIENT_SECRET",
        "FOS_OPENAI_API_KEY",
        "FOS_SLACK_BOT_TOKEN",
        "FOS_SLACK_CHANNEL_ID",
        "FOS_TELEGRAM_BOT_TOKEN",
        "FOS_TELEGRAM_CHAT_ID",
    }
)


@dataclass(frozen=True)
class OperatorOutputSafetyDiagnostics:
    unsafe_pattern_count: int
    unsafe_pattern_classes: tuple[str, ...]
    raw_hash_shaped_value_count: int
    url_like_value_count: int
    email_like_value_count: int
    secret_like_value_count: int
    payload_like_value_count: int
    unsafe_json_flag_count: int

    @property
    def safe(self) -> bool:
        return self.unsafe_pattern_count == 0

    def as_dict(self) -> dict[str, int | bool | list[str]]:
        return {
            "safe": self.safe,
            "unsafe_pattern_count": self.unsafe_pattern_count,
            "unsafe_pattern_classes": list(self.unsafe_pattern_classes),
            "raw_hash_shaped_value_count": self.raw_hash_shaped_value_count,
            "url_like_value_count": self.url_like_value_count,
            "email_like_value_count": self.email_like_value_count,
            "secret_like_value_count": self.secret_like_value_count,
            "payload_like_value_count": self.payload_like_value_count,
            "unsafe_json_flag_count": self.unsafe_json_flag_count,
        }


def inspect_operator_output(value: Any) -> OperatorOutputSafetyDiagnostics:
    counts = _empty_counts()
    for key, child in _walk(value):
        if key is not None:
            _inspect_key(str(key), child, counts)
        if isinstance(child, str):
            _inspect_string(child, counts)

    unsafe_pattern_count = sum(counts.values())
    unsafe_classes = tuple(
        sorted(class_name for class_name, count in counts.items() if count > 0)
    )
    return OperatorOutputSafetyDiagnostics(
        unsafe_pattern_count=unsafe_pattern_count,
        unsafe_pattern_classes=unsafe_classes,
        raw_hash_shaped_value_count=counts["raw_hash_shaped_value"],
        url_like_value_count=counts["url_like_value"],
        email_like_value_count=counts["email_like_value"],
        secret_like_value_count=counts["secret_like_value"],
        payload_like_value_count=counts["payload_like_value"],
        unsafe_json_flag_count=sum(
            counts[class_name] for class_name in UNSAFE_JSON_FLAG_CLASSES
        ),
    )


def assert_operator_output_safe(value: Any) -> OperatorOutputSafetyDiagnostics:
    diagnostics = inspect_operator_output(value)
    if not diagnostics.safe:
        raise ValueError("operator_output_unsafe")
    return diagnostics


def _empty_counts() -> dict[str, int]:
    counts = {
        "database_connection_like": 0,
        "email_like_value": 0,
        "payload_like_value": 0,
        "raw_hash_shaped_value": 0,
        "secret_like_value": 0,
        "url_like_value": 0,
    }
    counts.update({class_name: 0 for class_name in UNSAFE_JSON_FLAG_CLASSES})
    return counts


def _walk(value: Any) -> list[tuple[str | None, Any]]:
    visited: list[tuple[str | None, Any]] = []

    def visit(child: Any, key: str | None = None) -> None:
        visited.append((key, child))
        if isinstance(child, Mapping):
            for nested_key, nested_value in child.items():
                visit(nested_value, str(nested_key))
        elif isinstance(child, Sequence) and not isinstance(
            child,
            (bytes, bytearray, str),
        ):
            for nested_value in child:
                visit(nested_value)

    visit(value)
    return visited


def _inspect_key(key: str, value: Any, counts: dict[str, int]) -> None:
    if value is False or value is None:
        return

    normalized = key.casefold()
    if normalized == "unsafe_pattern_classes" or normalized.endswith("_count"):
        return
    if normalized in SAFE_DIAGNOSTIC_CLASS_VALUES:
        return
    for class_name, markers in UNSAFE_JSON_FLAG_CLASSES.items():
        if any(marker in normalized for marker in markers):
            counts[class_name] += 1

    if SECRET_RE.search(normalized):
        counts["secret_like_value"] += 1
    if RAW_PAYLOAD_RE.search(normalized):
        counts["payload_like_value"] += 1
    if URL_RE.search(normalized):
        counts["url_like_value"] += 1
    if DATABASE_RE.search(normalized):
        counts["database_connection_like"] += 1


def _inspect_string(value: str, counts: dict[str, int]) -> None:
    if value in SAFE_DIAGNOSTIC_CLASS_VALUES or value in SAFE_ENVIRONMENT_VARIABLE_NAMES:
        return

    counts["raw_hash_shaped_value"] += len(RAW_HASH_RE.findall(value))
    counts["url_like_value"] += len(URL_RE.findall(value))
    counts["email_like_value"] += len(EMAIL_RE.findall(value))
    counts["secret_like_value"] += len(SECRET_RE.findall(value))
    counts["payload_like_value"] += len(RAW_PAYLOAD_RE.findall(value))
    counts["database_connection_like"] += len(DATABASE_RE.findall(value))

    normalized = value.casefold()
    for class_name, markers in UNSAFE_JSON_FLAG_CLASSES.items():
        if any(marker in normalized for marker in markers):
            counts[class_name] += 1
