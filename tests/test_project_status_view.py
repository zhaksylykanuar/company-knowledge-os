from __future__ import annotations

from datetime import datetime, timezone

from app.services.project_status_view import (
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
