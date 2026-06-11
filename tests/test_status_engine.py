from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal, engine
from app.db.status_models import StatusSnapshotRecord
from app.services.project_status_view import (
    JiraIssueSnapshot,
    PullRequestSnapshot,
    RepoActivity,
)
from app.services.status_engine import (
    STATUS_GREEN,
    STATUS_RED,
    STATUS_UNKNOWN,
    STATUS_YELLOW,
    StatusSnapshot,
    build_project_status_snapshot,
)
from app.services.status_snapshot_repository import (
    get_latest_status_snapshot,
    save_status_snapshot,
)

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


def _snap(
    key: str,
    *,
    status: str = "In Progress",
    assignee: str = "Person A",
    days_ago: int = 1,
    duedate: str | None = None,
    title: str = "Project Alpha task",
) -> JiraIssueSnapshot:
    return JiraIssueSnapshot(
        issue_key=key,
        title=title,
        status=status,
        assignee=assignee,
        updated_at=NOW - timedelta(days=days_ago),
        duedate=duedate,
    )


def _pr(
    pr_id: str,
    *,
    days_ago: int = 0,
    jira_keys: tuple[str, ...] = (),
    state: str = "open",
    merged: bool = False,
) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        pr_id=pr_id,
        title="Project Alpha PR",
        state=state,
        merged=merged,
        author="person-a",
        updated_at=NOW - timedelta(days=days_ago),
        jira_keys=jira_keys,
        review_requested=True,
    )


def _activity(**overrides: object) -> RepoActivity:
    base = {
        "repo_names": ("project-alpha-api",),
        "open_prs": (),
        "merged_prs": (),
        "commit_count_7d": 0,
        "commit_jira_keys_7d": frozenset(),
        "pr_jira_keys": frozenset(),
    }
    base.update(overrides)
    return RepoActivity(**base)


def _build(
    snapshots: list[JiraIssueSnapshot],
    *,
    repo_activity: RepoActivity | None = None,
    previous_snapshot: StatusSnapshot | None = None,
) -> StatusSnapshot:
    return build_project_status_snapshot(
        project_entity_id="project:alpha",
        project_name="Project Alpha",
        jira_keys=["ALPHA"],
        snapshots=snapshots,
        repo_activity=repo_activity,
        previous_snapshot=previous_snapshot,
        now=NOW,
    )


def test_green_status_when_progress_is_fresh_and_unblocked() -> None:
    snapshot = _build(
        [_snap("ALPHA-101")],
        repo_activity=_activity(
            commit_count_7d=1,
            commit_jira_keys_7d=frozenset({"ALPHA-101"}),
        ),
    )

    assert snapshot.status_color == STATUS_GREEN
    assert snapshot.confidence == 1.0
    assert snapshot.blockers == ()
    assert snapshot.risks == ()
    assert snapshot.conflicts == ()
    assert snapshot.evidence_source_ids == (
        "github:commits:7d",
        "jira:issue:ALPHA-101",
    )


def test_yellow_status_for_stale_missing_owner_work_and_lower_confidence() -> None:
    snapshot = _build(
        [
            _snap(
                "ALPHA-101",
                assignee="unassigned",
                days_ago=20,
                title="Project Alpha stale work",
            )
        ]
    )

    assert snapshot.status_color == STATUS_YELLOW
    assert snapshot.confidence == 0.35
    assert {risk["type"] for risk in snapshot.risks} == {
        "missing_owner",
        "stale_issue",
    }
    assert "stale open Jira issues reduce confidence" in snapshot.confidence_reason
    assert "missing owners reduce confidence" in snapshot.confidence_reason


def test_red_status_for_missed_deadline() -> None:
    snapshot = _build(
        [
            _snap(
                "ALPHA-101",
                duedate="2026-06-01",
                title="Project Alpha release task",
            )
        ]
    )

    assert snapshot.status_color == STATUS_RED
    assert snapshot.confidence == 0.9
    assert snapshot.blockers[0]["type"] == "overdue"
    assert snapshot.recommendations[0]["id"] == "resolve_blockers"


def test_unknown_status_when_no_project_status_data_exists() -> None:
    snapshot = _build([])

    assert snapshot.status_color == STATUS_UNKNOWN
    assert snapshot.confidence == 0.2
    assert snapshot.current_work == ()
    assert snapshot.recommendations[0]["id"] == "sync_jira"


def test_conflicts_are_reported_from_jira_github_mismatch() -> None:
    snapshot = _build(
        [_snap("ALPHA-101")],
        repo_activity=_activity(open_prs=(_pr("org/repo/pull/7"),)),
    )

    assert snapshot.status_color == STATUS_YELLOW
    assert {conflict["type"] for conflict in snapshot.conflicts} == {
        "github_pr_without_jira",
        "jira_in_progress_without_code",
    }
    assert snapshot.confidence == 0.7


def test_what_changed_diffs_against_previous_snapshot() -> None:
    previous = _build(
        [_snap("ALPHA-101")],
        repo_activity=_activity(
            commit_count_7d=1,
            commit_jira_keys_7d=frozenset({"ALPHA-101"}),
        ),
    )

    current = _build(
        [
            _snap("ALPHA-101", status="Done", title="Project Alpha completed task"),
            _snap(
                "ALPHA-102",
                assignee="unassigned",
                days_ago=20,
                title="Project Alpha stale task",
            ),
        ],
        previous_snapshot=previous,
    )

    assert current.status_color == STATUS_YELLOW
    assert {
        (change["field"], change["change"])
        for change in current.what_changed
    } >= {
        ("status_color", "changed"),
        ("confidence", "changed"),
        ("summary", "changed"),
        ("current_work", "added"),
        ("current_work", "removed"),
        ("risks", "added"),
    }
    assert {
        tuple(change["ids"])
        for change in current.what_changed
        if change["field"] == "current_work"
    } == {("ALPHA-102",), ("ALPHA-101",)}


async def test_status_snapshot_repository_returns_latest_saved_snapshot() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(StatusSnapshotRecord.__table__.create, checkfirst=True)

    organization_id = f"test-org-{uuid4().hex}"
    try:
        first = _build([_snap("ALPHA-101")])
        second = _build([_snap("ALPHA-101", duedate="2026-06-01")])
        async with AsyncSessionLocal() as session:
            await save_status_snapshot(
                session,
                _with_organization(first, organization_id),
            )
            saved_second = await save_status_snapshot(
                session,
                _with_organization(second, organization_id),
            )
            latest = await get_latest_status_snapshot(
                session,
                organization_id=organization_id,
                entity_type="project",
                entity_id="project:alpha",
            )
            await session.commit()

        assert latest is not None
        assert latest.id == saved_second.id
        assert latest.status_color == STATUS_RED
        assert latest.blockers_json[0]["type"] == "overdue"
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(StatusSnapshotRecord).where(
                    StatusSnapshotRecord.organization_id == organization_id
                )
            )
            await session.commit()


def _with_organization(
    snapshot: StatusSnapshot,
    organization_id: str,
) -> StatusSnapshot:
    return StatusSnapshot(
        organization_id=organization_id,
        entity_type=snapshot.entity_type,
        entity_id=snapshot.entity_id,
        status_color=snapshot.status_color,
        summary=snapshot.summary,
        what_changed=snapshot.what_changed,
        current_work=snapshot.current_work,
        blockers=snapshot.blockers,
        risks=snapshot.risks,
        conflicts=snapshot.conflicts,
        recommendations=snapshot.recommendations,
        confidence=snapshot.confidence,
        confidence_reason=snapshot.confidence_reason,
        last_meaningful_update_at=snapshot.last_meaningful_update_at,
        evidence_source_ids=snapshot.evidence_source_ids,
    )
