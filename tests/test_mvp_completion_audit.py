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


def test_completion_contract_tracks_company_world_not_retired_audit_route() -> None:
    audit = run_mvp_completion_audit()
    local_keys = {item.key for item in audit.local_items}

    assert "company_world_view" in local_keys
    assert "repo_audit_view" not in local_keys


def test_completion_contract_treats_local_runtime_as_mvp_evidence() -> None:
    audit = run_mvp_completion_audit()
    all_items = {item.key: item for item in audit.items}

    assert all_items["local_full_stack_runtime"].evidence_present is True
    assert all_items["local_full_stack_runtime"].human_gated is True
    assert "staging_prod_deployment" not in all_items


def test_company_world_completion_requires_wiring_not_empty_files(
    tmp_path: Path,
) -> None:
    paths = (
        "web/components/CompanyWorldPanel.tsx",
        "web/app/company-brain/page.tsx",
        "app/api/company_map.py",
        "app/main.py",
        "app/services/company_map_read_service.py",
    )
    for relpath in paths:
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    audit = run_mvp_completion_audit(root=tmp_path)
    company_world = next(
        item for item in audit.items if item.key == "company_world_view"
    )

    assert company_world.evidence_present is False
    assert any(
        "app.include_router(company_map_router" in item
        for item in company_world.missing_evidence
    )
    assert any(
        "<CompanyWorldPanel" in item for item in company_world.missing_evidence
    )


def test_human_gated_items_are_code_ready_but_not_fully_complete() -> None:
    audit = run_mvp_completion_audit()

    human_keys = {item.key for item in audit.human_gated_items}
    # Hosting is no longer an MVP gate. Live provider access and the first real
    # external result remain explicit human-owned operations.
    assert human_keys == {
        "local_full_stack_runtime",
        "flow_connect_github",
        "flow_sync_github",
        "flow_external_action_result",
    }

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
    assert report["assessment_scope"] == "repository_evidence_only"
    assert report["repository_evidence_complete"] is True
    assert report["runtime_acceptance_assessed"] is False
    assert report["provider_calls"] is False
    assert report["reads_secrets"] is False
    assert report["summary"]["local_present"] == report["summary"]["local_total"]


def test_repo_root_points_at_repository() -> None:
    # The default root should resolve to the repository (contains the playbook).
    assert (REPO_ROOT / "founderOS_MASTER_PLAYBOOK.md").is_file()
