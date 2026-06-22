from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.jira_operating_model import (
    COMPONENT_STRATEGY_REPO,
    MODEL_COMPACT,
    MODEL_PORTFOLIO_PROGRAM,
    MODEL_PRODUCT_AREA,
    jira_operating_model_summary,
    recommended_model_class,
)
from app.services.operator_output_sanitizer import inspect_operator_output

REPO_ROOT = Path(__file__).resolve().parents[1]


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://jira-operating-model.invalid/path",
        "operator" + "@" + "jira-operating-model.invalid",
        "bot_token operating model value",
        "a" * 64,
        "postgres" + "://jira-operating-model.invalid/db",
        "provider_payload operating model body",
        "source_object_id operating model body",
        "PROJECT" + "-123",
        "issue title operating model body",
    )


def _assert_safe(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True


def test_jira_operating_model_summary_is_classes_and_counts_only() -> None:
    summary = jira_operating_model_summary()

    assert summary["recommended_model_class"] == MODEL_PRODUCT_AREA
    assert summary["recommended_project_class_count"] == 6
    assert summary["recommended_issue_type_class_count"] == 8
    assert summary["recommended_workflow_status_class_count"] == 8
    assert summary["repo_component_strategy"] == COMPONENT_STRATEGY_REPO
    assert summary["recommended_priority_class_count"] == 5
    assert summary["governance_rule_count"] == 7
    assert summary["jira_write_operations"] == "disabled"
    assert summary["no_send"] is True
    assert summary["no_source_of_truth_mutation"] is True
    assert summary["scheduler_execution"] == "disabled"
    _assert_safe(summary)


def test_recommended_model_class_scales_by_safe_counts() -> None:
    assert recommended_model_class(1) == MODEL_COMPACT
    assert recommended_model_class(7) == MODEL_PRODUCT_AREA
    assert recommended_model_class(11) == MODEL_PORTFOLIO_PROGRAM


def test_jira_target_blueprint_keeps_repositories_as_components() -> None:
    blueprint = (REPO_ROOT / "docs" / "ops" / "jira-target-blueprint.md").read_text(
        encoding="utf-8"
    )
    collapsed_blueprint = " ".join(blueprint.split())

    assert "Repositories are not Jira projects" in collapsed_blueprint
    assert "this does not create one Jira project per repository" in collapsed_blueprint
    assert "## 5. Components (repo \u2192 area project component)" in blueprint
    assert "## 5. Components (repo \u2194 project)" not in blueprint
