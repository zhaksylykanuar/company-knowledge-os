from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.models import IngestedEvent
from app.services.github_graph_mapping import (
    persist_github_repo_mapping,
    repo_entity_id,
)
from app.services import telegram_founder_bot as bot
from app.services.telegram_founder_bot import (
    HELP_REPLY,
    build_dev_reply_text,
    build_reply_for_update,
    parse_founder_command,
)
from scripts.sync_github_activity import build_pr_connector_payload
from scripts.sync_jira_issues import ingest_issue_payloads
from tests.test_telegram_status_snapshots import (
    NOW,
    PROJECT_ALPHA_ID,
    PROJECT_BETA_ID,
    _cleanup,
    _ensure_tables,
    _ingest_issue,
    _latest_snapshot_count,
    _seed_project,
)

ORG = "example-org"


async def _cleanup_github_repo(*, org: str, repo: str) -> None:
    source_id = repo_entity_id(org, repo)
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceEvent).where(SourceEvent.source_object_id.like(f"{org}/{repo}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.source_object_id.like(f"{org}/{repo}%")
            )
        )
        await session.execute(
            delete(EntityLinkRecord).where(EntityLinkRecord.from_entity_id == source_id)
        )
        await session.execute(
            delete(EntityRecord).where(EntityRecord.entity_id == source_id)
        )
        await session.commit()


async def _seed_github_repo(*, project_entity_id: str, org: str, repo: str) -> None:
    async with AsyncSessionLocal() as session:
        await persist_github_repo_mapping(
            session,
            org=org,
            mapping={repo: project_entity_id},
        )
        await session.commit()


async def _ingest_open_pr_without_jira(*, org: str, repo: str) -> None:
    payload = build_pr_connector_payload(
        {
            "number": 7,
            "state": "open",
            "merged_at": None,
            "updated_at": "2026-06-12T09:00:00Z",
            "title": "Review deployment setup",
            "head": {"ref": "feature/no-ticket"},
            "user": {"login": "Person A"},
            "requested_reviewers": [{"login": "Person A"}],
        },
        org=org,
        repo=repo,
    )
    assert payload is not None
    await ingest_issue_payloads([payload])


async def test_dev_command_renders_engineering_overview_with_evidence() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    repo = f"repo-alpha-api-{uuid4().hex[:8]}"
    await _ensure_tables()
    await _cleanup_github_repo(org=ORG, repo=repo)
    await _cleanup(organization_id)
    try:
        await _seed_project(
            project_entity_id=PROJECT_ALPHA_ID,
            project_name="Project Alpha",
            jira_key="ALPHA",
        )
        await _seed_project(
            project_entity_id=PROJECT_BETA_ID,
            project_name="Project Beta",
            jira_key="BETA",
        )
        await _seed_github_repo(
            project_entity_id=PROJECT_ALPHA_ID,
            org=ORG,
            repo=repo,
        )
        await _ingest_issue(
            "ALPHA-101",
            updated="2026-05-20T10:00:00+00:00",
            summary="Project Alpha integration task",
        )
        await _ingest_open_pr_without_jira(org=ORG, repo=repo)

        text = await build_dev_reply_text(now=NOW, organization_id=organization_id)

        assert text.startswith("🛠 Engineering overview")
        assert "• Project Alpha — code: 0 commits/7d, 1 open PR, 0 merged" in text
        assert "Jira: 1 issues, 1 open, stale 1, overdue 0" in text
        assert "Signals: blockers 0, risks 1, conflicts 2" in text
        assert "Second opinion: Jira In Progress without code: ALPHA-101" in text
        assert "+1 more conflict" in text
        assert "Project Beta" not in text
        assert "⚪" not in text
        assert await _latest_snapshot_count(organization_id, PROJECT_ALPHA_ID) == 1
        assert await _latest_snapshot_count(organization_id, PROJECT_BETA_ID) == 1
    finally:
        await _cleanup_github_repo(org=ORG, repo=repo)
        await _cleanup(organization_id)


async def test_dev_command_empty_state_has_no_project_noise(monkeypatch) -> None:
    async def fake_dev_overviews(*_args, **_kwargs):
        return []

    monkeypatch.setattr(bot, "_build_all_project_dev_overviews", fake_dev_overviews)
    update = {
        "update_id": 1,
        "message": {"chat": {"id": "777"}, "text": "/dev"},
    }

    reply = await build_reply_for_update(
        update,
        allowed_chat_id="777",
        now=datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert reply is not None
    assert reply.startswith("🛠 Engineering overview")
    assert "No project engineering evidence yet." in reply
    assert "Project Alpha" not in reply
    assert "Project Beta" not in reply
    assert "⚪" not in reply


def test_dev_command_is_routed_and_listed_in_help() -> None:
    assert parse_founder_command("/dev") == "dev"
    assert parse_founder_command("/dev@founderos_bot") == "dev"
    assert "/dev — инженерный обзор Jira↔GitHub по проектам" in HELP_REPLY
    assert "Скоро: /dev" not in HELP_REPLY
