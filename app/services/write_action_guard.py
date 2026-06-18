"""Write-action approval guardrail.

Read connectors already run behind execution acks. *Writes* to external
sources (Jira, GitHub) must additionally be backed by an explicit founder
approval. This module is the single enforcement point a write call site goes
through: no external write executes unless

1. the write-actions feature is enabled (``enable_write_actions``);
2. a matching founder approval has been granted for this exact write boundary
   (an :class:`~app.db.agent_models.AgentProposal` the founder accepted); and
3. the live-provider execution ack is present.

It composes :mod:`app.services.provider_execution_guard` ("can we talk to the
provider live at all") with the existing proposal queue ("the founder accepted
*this* write"). The guard stays pure and synchronous so it is trivial to unit
test and impossible to bypass; binding to a persisted proposal happens at the
call site via :func:`write_approval_from_proposal`.

A source agent that wants to write files an ``AgentProposal`` with
``kind == WRITE_ACTION_PROPOSAL_KIND`` and a payload carrying
``WRITE_APPROVAL_BOUNDARY_FIELD``; the founder accepts it in the inbox; the
agent then executes through :func:`require_approved_write_action`, passing the
accepted proposal. Nothing here calls a provider or mutates data — it only
decides whether a write is allowed to proceed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.provider_execution_guard import (
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)

# --- Reason codes -------------------------------------------------------
WRITE_ACTION_ALLOWED = "write_action_allowed"
WRITE_ACTION_FEATURE_DISABLED = "write_action_feature_disabled"
WRITE_ACTION_APPROVAL_REQUIRED = "write_action_approval_required"
WRITE_ACTION_APPROVAL_NOT_GRANTED = "write_action_approval_not_granted"
WRITE_ACTION_APPROVAL_MISMATCH = "write_action_approval_mismatch"

# --- Proposal contract shared with the approval inbox -------------------
WRITE_ACTION_PROPOSAL_KIND = "external_write_action"
WRITE_APPROVAL_BOUNDARY_FIELD = "write_boundary"

# Proposal statuses (from app.services.agent_proposals) that authorize a write.
# ``accepted`` = founder approved, not yet executed; ``applied`` = executed once
# already (kept so an idempotent re-run of the same approved action still
# passes the guard rather than failing closed mid-retry).
APPROVED_PROPOSAL_STATUSES = frozenset({"accepted", "applied"})

# --- Write boundary registry (provider write operations only) -----------
# These are deliberately distinct from the read/event boundaries in
# provider_execution_guard so a read ack can never authorize a write.
JIRA_CREATE_PROJECT = "jira_create_project"
JIRA_CREATE_COMPONENT = "jira_create_component"
JIRA_CREATE_ISSUE = "jira_create_issue"
JIRA_UPDATE_ISSUE = "jira_update_issue"
JIRA_TRANSITION_ISSUE = "jira_transition_issue"
JIRA_COMMENT_ISSUE = "jira_comment_issue"

GITHUB_CREATE_ISSUE = "github_create_issue"
GITHUB_UPDATE_ISSUE = "github_update_issue"
GITHUB_COMMENT_ISSUE = "github_comment_issue"
GITHUB_CREATE_PULL_REQUEST = "github_create_pull_request"
GITHUB_UPDATE_REPOSITORY = "github_update_repository"
GITHUB_TRANSFER_REPOSITORY = "github_transfer_repository"

UNKNOWN_WRITE_BOUNDARY = "external_write_boundary"
UNKNOWN_WRITE_PROVIDER = "external_provider"

_JIRA_WRITE_BOUNDARIES = frozenset(
    {
        JIRA_CREATE_PROJECT,
        JIRA_CREATE_COMPONENT,
        JIRA_CREATE_ISSUE,
        JIRA_UPDATE_ISSUE,
        JIRA_TRANSITION_ISSUE,
        JIRA_COMMENT_ISSUE,
    }
)
_GITHUB_WRITE_BOUNDARIES = frozenset(
    {
        GITHUB_CREATE_ISSUE,
        GITHUB_UPDATE_ISSUE,
        GITHUB_COMMENT_ISSUE,
        GITHUB_CREATE_PULL_REQUEST,
        GITHUB_UPDATE_REPOSITORY,
        GITHUB_TRANSFER_REPOSITORY,
    }
)
SAFE_WRITE_BOUNDARIES = _JIRA_WRITE_BOUNDARIES | _GITHUB_WRITE_BOUNDARIES


@dataclass(frozen=True)
class WriteApproval:
    """A founder decision on a single write action.

    Built from an accepted ``AgentProposal`` via
    :func:`write_approval_from_proposal`. ``status`` carries the proposal
    status verbatim; only :data:`APPROVED_PROPOSAL_STATUSES` authorize a write.
    """

    approval_id: str
    status: str
    boundary: str


@dataclass(frozen=True)
class WriteActionDiagnostics:
    provider: str
    boundary: str
    reason_code: str
    allowed: bool
    approval_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "boundary": self.boundary,
            "reason_code": self.reason_code,
            "allowed": self.allowed,
            "approval_id": self.approval_id,
        }


class WriteActionBlockedError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        boundary: str,
        reason_code: str,
        approval_id: str | None = None,
    ) -> None:
        super().__init__(reason_code)
        self.diagnostics = WriteActionDiagnostics(
            provider=provider,
            boundary=boundary,
            reason_code=reason_code,
            allowed=False,
            approval_id=approval_id,
        )

    @property
    def reason_code(self) -> str:
        return self.diagnostics.reason_code


def require_approved_write_action(
    *,
    boundary: str,
    enable_write_actions: bool,
    require_approval_for_writes: bool = True,
    approval: WriteApproval | None = None,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> WriteActionDiagnostics:
    """Authorize a single external write, or raise ``WriteActionBlockedError``.

    Fail-closed: every layer must pass. Returns sanitized diagnostics (no raw
    payload, no provider content) describing the allowed write.
    """

    safe_boundary = _safe_write_boundary(boundary)
    provider = _boundary_provider(safe_boundary)

    if enable_write_actions is not True:
        raise WriteActionBlockedError(
            provider=provider,
            boundary=safe_boundary,
            reason_code=WRITE_ACTION_FEATURE_DISABLED,
        )

    if require_approval_for_writes:
        if approval is None:
            raise WriteActionBlockedError(
                provider=provider,
                boundary=safe_boundary,
                reason_code=WRITE_ACTION_APPROVAL_REQUIRED,
            )
        if approval.status not in APPROVED_PROPOSAL_STATUSES:
            raise WriteActionBlockedError(
                provider=provider,
                boundary=safe_boundary,
                reason_code=WRITE_ACTION_APPROVAL_NOT_GRANTED,
                approval_id=approval.approval_id or None,
            )
        if _safe_write_boundary(approval.boundary) != safe_boundary:
            raise WriteActionBlockedError(
                provider=provider,
                boundary=safe_boundary,
                reason_code=WRITE_ACTION_APPROVAL_MISMATCH,
                approval_id=approval.approval_id or None,
            )

    try:
        require_live_provider_execution_ack(
            provider=provider,
            boundary=safe_boundary,
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
        )
    except ProviderExecutionBlockedError as exc:
        raise WriteActionBlockedError(
            provider=provider,
            boundary=safe_boundary,
            reason_code=exc.reason_code,
            approval_id=approval.approval_id if approval else None,
        ) from exc

    return WriteActionDiagnostics(
        provider=provider,
        boundary=safe_boundary,
        reason_code=WRITE_ACTION_ALLOWED,
        allowed=True,
        approval_id=approval.approval_id if approval else None,
    )


def write_approval_from_proposal(proposal: Any) -> WriteApproval:
    """Build a :class:`WriteApproval` from a persisted ``AgentProposal`` row.

    The proposal payload must declare :data:`WRITE_APPROVAL_BOUNDARY_FIELD`;
    the proposal's status is the founder's decision. Missing fields collapse to
    empty strings so the guard fails closed (no boundary match, not approved).
    """

    payload = getattr(proposal, "payload", None) or {}
    boundary = payload.get(WRITE_APPROVAL_BOUNDARY_FIELD, "") if isinstance(payload, dict) else ""
    return WriteApproval(
        approval_id=str(getattr(proposal, "proposal_id", "") or ""),
        status=str(getattr(proposal, "status", "") or ""),
        boundary=str(boundary or ""),
    )


def _safe_write_boundary(boundary: str) -> str:
    if boundary in SAFE_WRITE_BOUNDARIES:
        return boundary
    return UNKNOWN_WRITE_BOUNDARY


def _boundary_provider(safe_boundary: str) -> str:
    if safe_boundary in _JIRA_WRITE_BOUNDARIES:
        return "jira"
    if safe_boundary in _GITHUB_WRITE_BOUNDARIES:
        return "github"
    return UNKNOWN_WRITE_PROVIDER
