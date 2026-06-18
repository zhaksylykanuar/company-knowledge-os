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


# Every source type the platform knows about (founder may see them all).
KNOWN_SOURCE_TYPES = SOURCE_PERMISSIONS[SCOPE_FOUNDER]

# Per-audience disclosure flags — the single source of truth for what a
# redaction manifest asserts. A manifest lets investor/team views (and
# share packs) *prove* what they hide, for trust and leak tests.
_MANIFEST_SPEC: dict[str, dict[str, object]] = {
    SCOPE_FOUNDER: {
        "raw_refs_visible": True,
        "internal_notes_visible": True,
        "personal_team_details_visible": True,
        "finance_visible": True,
        "hidden_fields": (),
        "evidence_policy": "full",
    },
    SCOPE_TEAM: {
        "raw_refs_visible": False,
        "internal_notes_visible": False,
        "personal_team_details_visible": False,
        "finance_visible": False,
        "hidden_fields": ("note", "source_refs", "investor_private_notes"),
        "evidence_policy": "working_evidence_only",
    },
    SCOPE_INVESTOR: {
        "raw_refs_visible": False,
        "internal_notes_visible": False,
        "personal_team_details_visible": False,
        "finance_visible": False,
        "hidden_fields": (
            "evidence_refs",
            "source_refs",
            "note",
            "declared_state",
            "observed_state",
            "people_names",
        ),
        "evidence_policy": "aggregated_only",
    },
}


def redaction_manifest(
    viewer_scope: str,
    *,
    included_sections: list[str] | None = None,
    excluded_sections: list[str] | None = None,
) -> dict[str, object]:
    """An explicit, testable statement of what a view/pack redacts.

    Returns redaction_level, the section in/out lists, the field and
    source-type denylists for the audience, the evidence policy, and the
    four boolean disclosure flags (raw refs / internal notes / personal
    team details / finance). Investor and team always assert all four
    false; founder asserts all true.
    """

    spec = _MANIFEST_SPEC.get(viewer_scope, _MANIFEST_SPEC[SCOPE_INVESTOR])
    allowed_sources = set(SOURCE_PERMISSIONS.get(viewer_scope, ()))
    hidden_sources = [s for s in KNOWN_SOURCE_TYPES if s not in allowed_sources]
    return {
        "redaction_level": viewer_scope,
        "included_sections": list(included_sections or []),
        "excluded_sections": list(excluded_sections or []),
        "hidden_fields": list(spec["hidden_fields"]),
        "hidden_source_types": hidden_sources,
        "evidence_policy": spec["evidence_policy"],
        "raw_refs_visible": spec["raw_refs_visible"],
        "internal_notes_visible": spec["internal_notes_visible"],
        "personal_team_details_visible": spec["personal_team_details_visible"],
        "finance_visible": spec["finance_visible"],
    }


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
