"""FOS-007E: external write actions are blocked without founder approval.

These tests pin the fail-closed contract: a write to Jira/GitHub only proceeds
when the feature is enabled, a matching accepted proposal exists, and the
live-provider ack is present. They never call a provider.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.provider_execution_guard import LIVE_PROVIDER_EXECUTION_ACK
from app.services.write_action_guard import (
    GITHUB_CREATE_ISSUE,
    JIRA_CREATE_ISSUE,
    JIRA_CREATE_PROJECT,
    UNKNOWN_WRITE_BOUNDARY,
    WRITE_ACTION_ALLOWED,
    WRITE_ACTION_APPROVAL_MISMATCH,
    WRITE_ACTION_APPROVAL_NOT_GRANTED,
    WRITE_ACTION_APPROVAL_REQUIRED,
    WRITE_ACTION_FEATURE_DISABLED,
    WRITE_APPROVAL_BOUNDARY_FIELD,
    WriteActionBlockedError,
    WriteApproval,
    require_approved_write_action,
    write_approval_from_proposal,
)
from app.services.provider_execution_guard import (
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
)


def _approval(boundary: str = JIRA_CREATE_ISSUE, status: str = "accepted") -> WriteApproval:
    return WriteApproval(approval_id="prop-1", status=status, boundary=boundary)


def _granted(boundary: str = JIRA_CREATE_ISSUE):
    """All gates satisfied for the given write boundary."""
    return dict(
        boundary=boundary,
        enable_write_actions=True,
        approval=_approval(boundary),
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )


def test_feature_disabled_blocks_even_with_approval_and_ack() -> None:
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(
            boundary=JIRA_CREATE_ISSUE,
            enable_write_actions=False,
            approval=_approval(),
            allow_live_provider_execution=True,
            provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
        )
    assert exc.value.reason_code == WRITE_ACTION_FEATURE_DISABLED
    assert exc.value.diagnostics.allowed is False
    assert exc.value.diagnostics.provider == "jira"


def test_missing_approval_blocks() -> None:
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(
            boundary=JIRA_CREATE_ISSUE,
            enable_write_actions=True,
            approval=None,
            allow_live_provider_execution=True,
            provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
        )
    assert exc.value.reason_code == WRITE_ACTION_APPROVAL_REQUIRED


@pytest.mark.parametrize("status", ["pending", "rejected", "", "approved_typo"])
def test_unapproved_proposal_status_blocks(status: str) -> None:
    args = _granted()
    args["approval"] = _approval(status=status)
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(**args)
    assert exc.value.reason_code == WRITE_ACTION_APPROVAL_NOT_GRANTED


def test_approval_for_different_boundary_blocks() -> None:
    args = _granted(JIRA_CREATE_ISSUE)
    # Founder approved a project creation, not an issue creation.
    args["approval"] = _approval(boundary=JIRA_CREATE_PROJECT)
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(**args)
    assert exc.value.reason_code == WRITE_ACTION_APPROVAL_MISMATCH


def test_missing_live_ack_blocks() -> None:
    args = _granted()
    args["allow_live_provider_execution"] = False
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(**args)
    assert exc.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED


def test_wrong_ack_token_blocks() -> None:
    args = _granted()
    args["provider_execution_ack"] = "ALLOW EVERYTHING"
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(**args)
    assert exc.value.reason_code == PROVIDER_EXECUTION_ACK_REQUIRED


def test_fully_granted_write_is_allowed() -> None:
    diag = require_approved_write_action(**_granted(JIRA_CREATE_ISSUE))
    assert diag.allowed is True
    assert diag.reason_code == WRITE_ACTION_ALLOWED
    assert diag.provider == "jira"
    assert diag.boundary == JIRA_CREATE_ISSUE
    assert diag.approval_id == "prop-1"


def test_github_boundary_resolves_provider() -> None:
    diag = require_approved_write_action(**_granted(GITHUB_CREATE_ISSUE))
    assert diag.allowed is True
    assert diag.provider == "github"


def test_applied_status_still_authorizes_idempotent_retry() -> None:
    args = _granted()
    args["approval"] = _approval(status="applied")
    diag = require_approved_write_action(**args)
    assert diag.allowed is True


def test_approval_can_be_waived_by_policy_but_feature_and_ack_still_required() -> None:
    # require_approval_for_writes=False removes only the proposal requirement.
    diag = require_approved_write_action(
        boundary=JIRA_CREATE_ISSUE,
        enable_write_actions=True,
        require_approval_for_writes=False,
        approval=None,
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )
    assert diag.allowed is True
    assert diag.approval_id is None

    # ...but the live ack is still mandatory even when approval is waived.
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(
            boundary=JIRA_CREATE_ISSUE,
            enable_write_actions=True,
            require_approval_for_writes=False,
            approval=None,
            allow_live_provider_execution=False,
        )
    assert exc.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED


def test_unknown_boundary_is_sanitized_and_still_enforced() -> None:
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(
            boundary="rm -rf jira; drop table",
            enable_write_actions=True,
            approval=None,
            allow_live_provider_execution=True,
            provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
        )
    # Boundary collapses to a safe label; approval is still required.
    assert exc.value.diagnostics.boundary == UNKNOWN_WRITE_BOUNDARY
    assert exc.value.diagnostics.provider == "external_provider"
    assert exc.value.reason_code == WRITE_ACTION_APPROVAL_REQUIRED


def test_diagnostics_as_dict_is_a_fixed_safe_shape() -> None:
    diag = require_approved_write_action(**_granted())
    assert set(diag.as_dict()) == {
        "provider",
        "boundary",
        "reason_code",
        "allowed",
        "approval_id",
    }


def test_write_approval_from_proposal_reads_boundary_and_status() -> None:
    proposal = SimpleNamespace(
        proposal_id="prop-42",
        status="accepted",
        payload={WRITE_APPROVAL_BOUNDARY_FIELD: JIRA_CREATE_ISSUE, "title": "x"},
    )
    approval = write_approval_from_proposal(proposal)
    assert approval == WriteApproval(
        approval_id="prop-42", status="accepted", boundary=JIRA_CREATE_ISSUE
    )
    # And it authorizes the matching write end to end.
    diag = require_approved_write_action(
        boundary=JIRA_CREATE_ISSUE,
        enable_write_actions=True,
        approval=approval,
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )
    assert diag.allowed is True


def test_write_approval_from_proposal_missing_payload_fails_closed() -> None:
    proposal = SimpleNamespace(proposal_id="prop-9", status="accepted", payload=None)
    approval = write_approval_from_proposal(proposal)
    assert approval.boundary == ""
    # An approval with no declared boundary cannot match any real write.
    with pytest.raises(WriteActionBlockedError) as exc:
        require_approved_write_action(
            boundary=JIRA_CREATE_ISSUE,
            enable_write_actions=True,
            approval=approval,
            allow_live_provider_execution=True,
            provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
        )
    assert exc.value.reason_code == WRITE_ACTION_APPROVAL_MISMATCH
