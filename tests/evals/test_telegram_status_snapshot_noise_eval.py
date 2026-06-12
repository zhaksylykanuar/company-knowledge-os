from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from app.services.telegram_founder_bot import (
    _ProjectEntity,
    _render_all_project_snapshots,
)


@dataclass(frozen=True)
class TelegramStatusSnapshotNoiseEvalCase:
    case_id: str
    project_name_with_evidence: str
    project_name_without_evidence: str
    expected_visible: str
    expected_suppressed: str


NOISE_CASE = TelegramStatusSnapshotNoiseEvalCase(
    case_id="project_without_evidence_rendered_as_gray_unknown_in_status",
    project_name_with_evidence="Project Alpha",
    project_name_without_evidence="Project Beta",
    expected_visible="Project Alpha",
    expected_suppressed="Project Beta",
)


def _snapshot(
    *,
    status_color: str,
    evidence_source_ids: list[str],
    summary: str,
) -> Any:
    return SimpleNamespace(
        status_color=status_color,
        confidence=0.90 if evidence_source_ids else 0.20,
        what_changed=({"field": "snapshot", "change": "created"},),
        summary=summary,
        evidence_source_ids=tuple(evidence_source_ids),
    )


def test_project_without_evidence_is_not_rendered_as_gray_unknown_in_status() -> None:
    rendered = _render_all_project_snapshots(
        [
            (
                _ProjectEntity("project:alpha", NOISE_CASE.project_name_with_evidence),
                _snapshot(
                    status_color="green",
                    evidence_source_ids=["jira:issue:ALPHA-101"],
                    summary="Project Alpha: green; Jira ALPHA; 1 issues.",
                ),
            ),
            (
                _ProjectEntity("project:beta", NOISE_CASE.project_name_without_evidence),
                _snapshot(
                    status_color="unknown",
                    evidence_source_ids=[],
                    summary="Project Beta: unknown; Jira no Jira keys; 0 issues.",
                ),
            ),
        ]
    )

    assert NOISE_CASE.expected_visible in rendered
    assert NOISE_CASE.expected_suppressed not in rendered
    assert "⚪" not in rendered
    assert "unknown; Jira no Jira keys; 0 issues" not in rendered
