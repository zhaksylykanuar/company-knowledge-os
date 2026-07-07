"""Offline unit tests for the MVP completion audit.

These tests are pure and offline: no database, no network, no provider calls.
They pin the deterministic completion contract used to prove which MVP
requirements are locally satisfied and which remain human/external gated.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.mvp_completion_audit import (
    REPO_ROOT,
    run_mvp_completion_audit,
)


def test_current_repo_local_scope_is_complete() -> None:
    audit = run_mvp_completion_audit()

    # Every non-human-gated MVP requirement and main-flow step must have
    # authoritative evidence in the current tree.
    missing_local = [
        item.key for item in audit.local_items if not item.evidence_present
    ]
    assert missing_local == []
    assert audit.local_scope_complete is True


def test_human_gated_items_are_code_ready_but_not_fully_complete() -> None:
    audit = run_mvp_completion_audit()

    human_keys = {item.key for item in audit.human_gated_items}
    # The two honestly human/external-gated pieces of the MVP.
    assert human_keys == {"staging_prod_deployment", "flow_external_action_result"}

    # Their code paths exist locally...
    assert audit.code_ready_for_human_gated is True
    # ...but the full MVP is not proven complete while human steps remain.
    assert audit.fully_complete is False
    for item in audit.human_gated_items:
        assert item.status == "code_ready_human_gated"
        assert item.human_note


def test_missing_evidence_is_reported_against_empty_tree(tmp_path: Path) -> None:
    audit = run_mvp_completion_audit(root=tmp_path)

    # An empty tree must fail the local scope and list concrete missing markers.
    assert audit.local_scope_complete is False
    assert audit.fully_complete is False
    for item in audit.items:
        assert item.evidence_present is False
        assert item.missing_evidence


def test_audit_report_is_json_serializable_and_safe() -> None:
    report = run_mvp_completion_audit().to_dict()

    blob = json.dumps(report)
    # The audit must never surface secret-like values; it only names files.
    assert "PRIVATE_KEY" not in blob
    assert "API_AUTH_KEY" not in blob
    assert report["offline"] is True
    assert report["provider_calls"] is False
    assert report["reads_secrets"] is False
    assert report["summary"]["local_present"] == report["summary"]["local_total"]


def test_repo_root_points_at_repository() -> None:
    # The default root should resolve to the repository (contains the playbook).
    assert (REPO_ROOT / "founderOS_MASTER_PLAYBOOK.md").is_file()
