from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.graph_models import EntityLinkRecord, EntityRecord
from app.db.models import AuditLog, IngestedEvent
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.github_graph_mapping import (
    all_mapped_repos,
    persist_github_repo_mapping,
    repo_entity_id,
    repos_for_project,
)
from scripts.sync_github_activity import (
    _read_response_body,
    build_commit_connector_payload,
    build_pr_connector_payload,
    extract_jira_keys,
)
from scripts import sync_github_activity
from scripts.sync_jira_issues import ingest_issue_payloads
from tests.test_entity_resolution import _ensure_graph_tables, _seed

ORG = "example-org"


async def _ensure_source_control_tables() -> None:
    from app.db.base import engine

    async with engine.begin() as conn:
        for table in (
            AuditLog.__table__,
            SourceControlState.__table__,
            SourceRunRequest.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup_source_request(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SourceControlState).where(
                SourceControlState.last_request_key.like(f"%{marker}%")
            )
        )
        await session.commit()


async def _cleanup_repo(repo: str) -> None:
    source_id = repo_entity_id(ORG, repo)
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_object_id.like(f"{ORG}/{repo}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.source_object_id.like(f"{ORG}/{repo}%")
            )
        )
        await session.execute(
            delete(EntityLinkRecord).where(
                EntityLinkRecord.from_entity_id == source_id
            )
        )
        await session.execute(
            delete(EntityRecord).where(EntityRecord.entity_id == source_id)
        )
        await session.commit()


class _ChunkedResponse:
    """Fake HTTP response whose read(amt) returns less than requested."""

    def __init__(self, body: bytes, *, chunk_size: int) -> None:
        self._body = body
        self._chunk_size = chunk_size
        self._offset = 0

    def read(self, amt: int) -> bytes:
        size = min(amt, self._chunk_size)
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_read_response_body_reassembles_chunked_reads() -> None:
    body = b'{"items": "' + b"x" * 200_000 + b'"}'

    assert _read_response_body(_ChunkedResponse(body, chunk_size=1024)) == body


def test_read_response_body_rejects_oversized_response() -> None:
    response = _ChunkedResponse(b"y" * 300, chunk_size=100)

    with pytest.raises(RuntimeError, match="exceeds 250 bytes"):
        _read_response_body(response, max_bytes=250)


def test_extract_jira_keys() -> None:
    assert extract_jira_keys("QS-7 fix login", "feature/QT-12-auth", None) == [
        "QS-7",
        "QT-12",
    ]
    assert extract_jira_keys("no keys here") == []


def test_build_pr_payload_contract() -> None:
    payload = build_pr_connector_payload(
        {
            "number": 42,
            "state": "open",
            "merged_at": None,
            "updated_at": "2026-06-12T09:00:00Z",
            "title": "QS-7 add auth flow",
            "head": {"ref": "feature/QS-7-auth"},
            "user": {"login": "person-a"},
            "html_url": "https://example.invalid/pr/42",
            "requested_reviewers": [{"login": "person-b"}],
        },
        org=ORG,
        repo="repo-alpha-api",
    )

    assert payload is not None
    assert payload["event_type"] == "github.pull_request.synchronized"
    assert payload["source_object_id"] == f"{ORG}/repo-alpha-api/pull/42"
    assert payload["payload"]["jira_keys"] == ["QS-7"]
    assert payload["payload"]["review_requested"] is True

    merged = build_pr_connector_payload(
        {"number": 7, "state": "closed", "merged_at": "2026-06-10T00:00:00Z",
         "updated_at": "2026-06-10T00:00:00Z", "title": "x"},
        org=ORG,
        repo="repo-alpha-api",
    )
    assert merged is not None
    assert merged["event_type"] == "github.pull_request.merged"
    assert build_pr_connector_payload({}, org=ORG, repo="r") is None


def test_build_commit_payload_contract() -> None:
    payload = build_commit_connector_payload(
        {
            "sha": "a" * 40,
            "commit": {
                "message": "QT-12: fix sensor sync\n\ndetails",
                "author": {"name": "Person A", "date": "2026-06-11T08:00:00Z"},
            },
        },
        org=ORG,
        repo="repo-alpha-api",
    )

    assert payload is not None
    assert payload["event_type"] == "github.commit.pushed"
    assert payload["payload"]["title"] == "QT-12: fix sensor sync"
    assert payload["payload"]["jira_keys"] == ["QT-12"]
    assert payload["idempotency_key"].endswith("a" * 40)
    assert build_commit_connector_payload({}, org=ORG, repo="r") is None


async def test_repo_mapping_idempotent_and_ingest_counts() -> None:
    await _seed()
    repo = f"repo-test-{uuid4().hex[:6]}"
    await _cleanup_repo(repo)
    try:
        async with AsyncSessionLocal() as session:
            first = await persist_github_repo_mapping(
                session, org=ORG, mapping={repo: "project:qtwin"}
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            second = await persist_github_repo_mapping(
                session, org=ORG, mapping={repo: "project:qtwin"}
            )
            await session.commit()
            mapped = await all_mapped_repos(session)
            project_repos = await repos_for_project(session, "project:qtwin")

        assert first == {"entities_created": 1, "links_created": 1}
        assert second == {"entities_created": 0, "links_created": 0}
        assert {"org": ORG, "repo": repo, "project_entity_id": "project:qtwin"} in mapped
        assert {"org": ORG, "repo": repo} in project_repos

        payloads = [
            build_pr_connector_payload(
                {"number": 1, "state": "open", "merged_at": None,
                 "updated_at": "2026-06-12T09:00:00Z", "title": "QS-1 work"},
                org=ORG,
                repo=repo,
            ),
            build_commit_connector_payload(
                {"sha": "b" * 40, "commit": {"message": "QS-1 progress",
                 "author": {"name": "Person A", "date": "2026-06-12T08:00:00Z"}}},
                org=ORG,
                repo=repo,
            ),
        ]
        first_ingest = await ingest_issue_payloads([p for p in payloads if p])
        second_ingest = await ingest_issue_payloads([p for p in payloads if p])
        assert first_ingest == {"source_events_created": 2, "already_present": 0}
        assert second_ingest == {"source_events_created": 0, "already_present": 2}
    finally:
        await _cleanup_repo(repo)


async def test_repo_mapping_rejects_unknown_target() -> None:
    await _ensure_graph_tables()
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await persist_github_repo_mapping(
                session, org=ORG, mapping={"r": "project:nope"}
            )


async def test_github_sync_script_records_source_control_request_without_live_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = f"github-sync-script-{uuid4().hex[:8]}"
    await _ensure_source_control_tables()

    def fail_fetch(*args, **kwargs):
        raise AssertionError("compatibility script must not call GitHub directly")

    monkeypatch.setattr(sync_github_activity, "fetch_repo_activity", fail_fetch)
    try:
        args = sync_github_activity._parse_args(
            [
                "--confirm-sync",
                sync_github_activity.CONFIRM_SYNC_PHRASE,
                "--request-key",
                marker,
                "--max-results",
                "9",
                "--allow-live-readonly-apis",
                "--acknowledge-live-readonly-risk",
                "PRIVATE_ACK_DO_NOT_RETURN",
            ]
        )
        rc = await sync_github_activity._run(args)
        output = capsys.readouterr().out
        assert rc == 0
        assert "PRIVATE_ACK_DO_NOT_RETURN" not in output

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == marker
                )
            )
            assert row is not None
            assert row.source_type == "github"
            assert row.action_type == "sync"
            assert row.external_side_effect is False
            assert row.input_snapshot["input"]["legacy_script"] == (
                "scripts/sync_github_activity.py"
            )
            assert row.input_snapshot["input"]["max_results"] == 9
            assert row.input_snapshot["input"]["uses_configured_scope"] is True
            assert row.input_snapshot["input"]["live_readonly_requested"] is True
            assert row.input_snapshot["input"]["live_readonly_ack_supplied"] is True
    finally:
        await _cleanup_source_request(marker)
