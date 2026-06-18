"""Explicit live connector scopes/allowlists and limits.

A real Jira/GitHub sync/backfill must never read a whole org by accident. This
module centralizes the scope model (which projects/repos are allowed), the
limits applied to every live read, and the single ``sync_scope_block`` gate the
orchestrator uses.

Scope *values* (project keys, repo names) are not secrets and may be shown
sanitized. Tokens/credentials are never surfaced here.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.config import settings
from app.services.secret_patterns import contains_secret_value
from app.services.source_control import connector_setup_status

# External sources that require an explicit scope before any live read.
SCOPE_REQUIRED_SOURCES = {"jira", "github"}

# Wildcard-ish tokens that would mean "everything" — treated as too broad.
_WILDCARDS = {"*", "all", "any", "everything"}

_SCOPE_FIELDS = {
    "jira": "FOUNDEROS_JIRA_PROJECT_KEYS",
    "github": "FOUNDEROS_GITHUB_REPOS",
}
_SCOPE_LABEL = {"jira": "project_keys", "github": "repos"}


def _csv(value: str | None) -> list[str]:
    if not isinstance(value, str):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for part in value.split(","):
        item = part.strip()
        if not item or item in seen:
            continue
        # Never surface a secret-shaped value as a "scope".
        if contains_secret_value(item) or len(item) > 200:
            continue
        seen.add(item)
        out.append(item)
    return out


def _setting(config: Any, attr: str) -> str | None:
    value = getattr(config, attr, None)
    return value if isinstance(value, str) and value.strip() else None


def scope_values(source_type: str, config: Any = settings) -> list[str]:
    if source_type == "jira":
        return _csv(_setting(config, "jira_project_keys") or os.getenv("FOUNDEROS_JIRA_PROJECT_KEYS"))
    if source_type == "github":
        return _csv(
            _setting(config, "github_repos")
            or os.getenv("FOUNDEROS_GITHUB_REPOS")
            or os.getenv("GITHUB_REPOS")
        )
    return []


def scope_field_names(source_type: str) -> list[str]:
    field = _SCOPE_FIELDS.get(source_type)
    return [field] if field else []


def require_scope(config: Any = settings) -> bool:
    return bool(getattr(config, "require_connector_scope", True))


def scope_required(source_type: str, config: Any = settings) -> bool:
    return source_type in SCOPE_REQUIRED_SOURCES and require_scope(config)


def scope_configured(source_type: str, config: Any = settings) -> bool:
    if source_type not in SCOPE_REQUIRED_SOURCES:
        return True  # not applicable
    return bool(scope_values(source_type, config))


def scope_too_broad(source_type: str, config: Any = settings) -> bool:
    for value in scope_values(source_type, config):
        lowered = value.strip().casefold()
        if lowered in _WILDCARDS or lowered.endswith("/*") or lowered.endswith("/all"):
            return True
    return False


def connector_limits(config: Any = settings) -> dict[str, int]:
    return {
        "sync_limit": int(getattr(config, "connector_sync_limit", 50) or 50),
        "backfill_limit": int(getattr(config, "connector_backfill_limit", 100) or 100),
        "backfill_max_days": int(
            getattr(config, "connector_backfill_max_days", 30) or 30
        ),
    }


def scope_summary(source_type: str, config: Any = settings) -> dict[str, Any]:
    values = scope_values(source_type, config)
    summary: dict[str, Any] = {
        "count": len(values),
        "too_broad": scope_too_broad(source_type, config),
    }
    label = _SCOPE_LABEL.get(source_type)
    if label is not None:
        summary[label] = values[:25]
    return summary


def missing_scope_fields(source_type: str, config: Any = settings) -> list[str]:
    if scope_configured(source_type, config):
        return []
    return scope_field_names(source_type)


def scope_model(source_type: str, config: Any = settings) -> dict[str, Any]:
    required = scope_required(source_type, config)
    configured = scope_configured(source_type, config)
    return {
        "scope_required": required,
        "scope_configured": configured,
        "scope_summary": scope_summary(source_type, config)
        if source_type in SCOPE_REQUIRED_SOURCES
        else {"count": 0, "too_broad": False},
        "missing_scope_fields": missing_scope_fields(source_type, config),
        "scope_too_broad": scope_too_broad(source_type, config),
        "limits": connector_limits(config),
    }


def sync_scope_block(source_type: str, config: Any = settings) -> str | None:
    """Return ``"missing_scope"`` when a live sync/backfill/preview must be
    blocked for lack of an explicit scope; otherwise ``None``.

    Returns ``None`` when real connectors are disabled or the source is not
    configured — those are handled (real_disabled / missing_config) closer to
    the adapter, and must take precedence so the reason is accurate.
    """

    if not scope_required(source_type, config):
        return None
    if not bool(getattr(config, "enable_real_connectors", False)):
        return None
    if connector_setup_status(source_type) != "ready":
        return None
    if scope_configured(source_type, config):
        return None
    return "missing_scope"
