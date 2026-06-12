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
