"""Visibility scopes: founder / team / investor see different slices.

Single-workspace for now, but the boundary is fixed early so views
never accidentally share internal findings. ``redaction_rules`` and
``source_permissions`` are declared here as the future contract and
applied by read models when multi-view UI lands.
"""

from __future__ import annotations

SCOPE_FOUNDER = "founder"
SCOPE_TEAM = "team"
SCOPE_INVESTOR = "investor"

SCOPES = (SCOPE_FOUNDER, SCOPE_TEAM, SCOPE_INVESTOR)

# Founder sees everything; team sees team+investor; investor only investor.
_SCOPE_RANK = {SCOPE_FOUNDER: 2, SCOPE_TEAM: 1, SCOPE_INVESTOR: 0}

# Future contract: which sources a viewer scope may surface evidence from,
# and what gets redacted in lower scopes.
SOURCE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    SCOPE_FOUNDER: ("jira", "github", "gmail", "drive", "telegram", "manual"),
    SCOPE_TEAM: ("jira", "github", "drive", "manual"),
    SCOPE_INVESTOR: (),
}

REDACTION_RULES: dict[str, tuple[str, ...]] = {
    SCOPE_TEAM: ("client_names_in_risks",),
    SCOPE_INVESTOR: (
        "evidence_refs",
        "people_names",
        "client_names_in_risks",
        "internal_findings",
    ),
}


def can_view(viewer_scope: str, item_scope: str) -> bool:
    """A viewer sees items at their scope and below."""

    if viewer_scope not in _SCOPE_RANK or item_scope not in _SCOPE_RANK:
        return False
    return _SCOPE_RANK[viewer_scope] >= _SCOPE_RANK[item_scope]


# Fields stripped from finding read models per viewer scope. Investor
# additionally only ever sees items explicitly scoped to investor.
_TEAM_REDACTED_FIELDS = ("note", "source_refs")
_INVESTOR_ALLOWED_FIELDS = (
    "finding_key",
    "finding_type",
    "summary",
    "severity",
    "status",
    "created_at",
)


def redact_finding(finding: dict, viewer_scope: str) -> dict | None:
    """Apply scope filtering and field redaction to a finding read model.

    Audience-based, not hierarchical: a finding's ``visibility_scope`` is
    the audience it belongs to. The founder sees everything; team sees
    only team-scoped working items (with notes/source refs stripped);
    investor sees only investor-curated items reduced to safe fields.
    Returns None when the viewer must not see the item at all.
    """

    item_scope = str(finding.get("visibility_scope") or SCOPE_FOUNDER)
    if viewer_scope == SCOPE_FOUNDER:
        return finding
    if viewer_scope == SCOPE_TEAM:
        if item_scope != SCOPE_TEAM:
            return None
        redacted = dict(finding)
        for field in _TEAM_REDACTED_FIELDS:
            redacted.pop(field, None)
        return redacted
    if viewer_scope == SCOPE_INVESTOR:
        if item_scope != SCOPE_INVESTOR:
            return None
        return {key: finding.get(key) for key in _INVESTOR_ALLOWED_FIELDS}
    return None
