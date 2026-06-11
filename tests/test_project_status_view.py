from __future__ import annotations

from datetime import datetime, timezone

from app.services.project_status_view import (
    PullRequestSnapshot,
    RepoActivity,
    JiraIssueSnapshot,
    render_project_status_text,
    snapshot_from_payload,
)

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


def _snap(
    key: str,
    *,
    status: str = "In Progress",
    assignee: str = "Alisher",
    days_ago: int = 1,
    duedate: str | None = None,
    title: str = "Sample task",
) -> JiraIssueSnapshot:
    return JiraIssueSnapshot(
        issue_key=key,
        title=title,
        status=status,
        assignee=assignee,
        updated_at=NOW.replace(hour=0) if days_ago == 0 else NOW - __import__("datetime").timedelta(days=days_ago),
        duedate=duedate,
    )


def test_snapshot_from_payload_strips_key_prefix_and_parses_date() -> None:
    snap = snapshot_from_payload(
        "QS-7",
        {
            "title": "[QS-7] Fix login",
            "status": "In Progress",
            "actor_external_id": "Alisher",
            "updated": "2026-06-12T10:00:00.000+0000",
            "duedate": "2026-06-20",
        },
    )

    assert snap.title == "Fix login"
    assert snap.status == "In Progress"
    assert snap.updated_at is not None
    assert snap.updated_at.tzinfo is not None
    assert snap.is_done is False

    done = snapshot_from_payload("QS-8", {"title": "[QS-8] x", "status": "Done"})
    assert done.is_done is True


def test_render_sections_counts_stale_overdue_and_people() -> None:
    snapshots = [
        _snap("QS-1", days_ago=1),
        _snap("QS-2", days_ago=2, assignee="Daniyar"),
        _snap("QS-3", days_ago=30, title="Старая задача"),
        _snap("QS-4", days_ago=3, duedate="2026-06-01", title="Просроченная"),
        _snap("QS-5", status="Done", days_ago=1),
    ]

    text = render_project_status_text(
        project_name="qTwin",
        jira_keys=["QS", "QT"],
        snapshots=snapshots,
        now=NOW,
    )

    assert "📂 qTwin — статус по Jira (QS, QT)" in text
    assert "Всего: 5 задач (открытых 4, закрытых 1)" in text
    assert "без движения >14 дн: 1" in text
    assert "просрочено: 1" in text
    assert "🔧 Свежая активность" in text
    assert "🧊 Без движения >14 дней" in text
    assert "[QS-3] Старая задача" in text
    assert "⏰ Просрочено" in text
    assert "[QS-4] Просроченная" in text
    assert "👥 Открытые задачи по людям" in text
    assert "Alisher: 3" in text
    assert "Daniyar: 1" in text
    assert len(text) < 1800


def test_render_empty_suggests_sync() -> None:
    text = render_project_status_text(
        project_name="qTwin",
        jira_keys=["QS"],
        snapshots=[],
        now=NOW,
    )
    assert "Задачи ещё не синхронизированы" in text


def _activity(**kw) -> RepoActivity:
    base = dict(
        repo_names=("repo-alpha-api",),
        open_prs=(),
        merged_prs=(),
        commit_count_7d=0,
        commit_jira_keys_7d=frozenset(),
        pr_jira_keys=frozenset(),
    )
    base.update(kw)
    return RepoActivity(**base)


def _pr(pr_id: str, *, state: str = "open", merged: bool = False,
        days_ago: int = 0, jira_keys: tuple = (), title: str = "PR work") -> PullRequestSnapshot:
    import datetime as _dt
    return PullRequestSnapshot(
        pr_id=pr_id, title=title, state=state, merged=merged, author="person-a",
        updated_at=NOW - _dt.timedelta(days=days_ago),
        jira_keys=jira_keys, review_requested=True,
    )


def test_engineering_and_second_opinion_sections() -> None:
    snapshots = [
        _snap("QS-1", days_ago=1),                       # in progress, код есть
        _snap("QS-2", days_ago=2, title="Молчит"),       # in progress, кода нет
        _snap("QS-3", status="To Do", days_ago=3),
    ]
    activity = _activity(
        open_prs=(
            _pr("o/r/pull/1", days_ago=3, jira_keys=("QS-1",), title="QS-1 auth"),
            _pr("o/r/pull/2", days_ago=0, jira_keys=()),
        ),
        merged_prs=(_pr("o/r/pull/3", state="merged", merged=True,
                        days_ago=1, jira_keys=("QS-3",)),),
        commit_count_7d=5,
        commit_jira_keys_7d=frozenset({"QS-1"}),
    )

    text = render_project_status_text(
        project_name="qTwin", jira_keys=["QS"], snapshots=snapshots,
        repo_activity=activity, now=NOW,
    )

    assert "⚙️ Код (repo-alpha-api)" in text
    assert "Коммитов за 7 дн: 5 · открытых PR: 2 · merged: 1" in text
    assert "без движения 3 дн" in text          # stale review PR
    assert "🔍 Second opinion" in text
    assert "Jira In Progress: 2 задач, код за 7 дн виден по 1" in text
    assert "молчат: QS-2" in text
    assert "Открытых PR без Jira-задачи: 1" in text
    assert "PR merged, но задача не закрыта: QS-3" in text


def test_no_findings_renders_clean_second_opinion() -> None:
    text = render_project_status_text(
        project_name="qTwin", jira_keys=["QS"],
        snapshots=[_snap("QS-9", status="To Do", days_ago=1)],
        repo_activity=_activity(commit_count_7d=2),
        now=NOW,
    )
    assert "Расхождений Jira↔GitHub не найдено." in text
