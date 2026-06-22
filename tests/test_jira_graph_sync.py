from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.db.models import AuditLog, IngestedEvent
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.jira_graph_mapping import (
    all_mapped_jira_keys,
    jira_entity_id,
    jira_issue_count_for_keys,
    jira_keys_for_project,
    persist_jira_project_mapping,
)
from scripts.sync_jira_issues import (
    build_issue_connector_payload,
    fetch_jira_issues,
    ingest_issue_payloads,
)
from scripts import sync_jira_issues
from tests.test_entity_resolution import _ensure_graph_tables, _seed

ENVIRON = {
    "FOS_JIRA_READONLY_SITE": "example-team.atlassian.net",
    "FOS_JIRA_READONLY_USER": "reader@example.invalid",
    "FOS_JIRA_READONLY_TOKEN": "test-token-not-real",
}


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


def _issue(key: str, *, summary: str = "Sample issue", updated: str = "2026-06-12T10:00:00.000+0000") -> dict:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Test Assignee"},
            "updated": updated,
            "duedate": None,
            "priority": {"name": "Medium"},
            "issuetype": {"name": "Task"},
        },
    }


async def _cleanup_test_key(test_key: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_object_id.like(f"{test_key}-%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.source_object_id.like(f"{test_key}-%")
            )
        )
        await session.execute(
            delete(EntityLinkRecord).where(
                EntityLinkRecord.from_entity_id == jira_entity_id(test_key)
            )
        )
        await session.execute(
            delete(EntityAliasRecord).where(
                EntityAliasRecord.entity_id == jira_entity_id(test_key)
            )
        )
        await session.execute(
            delete(EntityRecord).where(
                EntityRecord.entity_id == jira_entity_id(test_key)
            )
        )
        await session.commit()


async def test_mapping_is_idempotent_and_queryable() -> None:
    await _seed()
    test_key = f"TQ{uuid4().hex[:4].upper()}"
    await _cleanup_test_key(test_key)
    try:
        async with AsyncSessionLocal() as session:
            first = await persist_jira_project_mapping(
                session, {test_key: "project:qtwin"}
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            second = await persist_jira_project_mapping(
                session, {test_key: "project:qtwin"}
            )
            await session.commit()

            keys = await jira_keys_for_project(session, "project:qtwin")
            mapped = await all_mapped_jira_keys(session)

        assert first["entities_created"] == 1
        assert first["links_created"] == 1
        assert second == {"entities_created": 0, "links_created": 0}
        assert test_key in keys
        assert mapped[test_key] == "project:qtwin"
    finally:
        await _cleanup_test_key(test_key)


async def test_mapping_rejects_unknown_target() -> None:
    await _ensure_graph_tables()
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await persist_jira_project_mapping(
                session, {"ZZZ": "project:does-not-exist"}
            )


def test_build_issue_connector_payload_contract() -> None:
    payload = build_issue_connector_payload(
        _issue("QS-7", summary="Fix login"),
        site="https://example-team.atlassian.net",
        jira_project_key="QS",
    )

    assert payload is not None
    assert payload["source_system"] == "jira"
    assert payload["source_object_id"] == "QS-7"
    assert payload["event_type"] == "jira.issue.updated"
    assert payload["idempotency_key"].startswith("jira-qs-7-updated-")
    assert payload["payload"]["title"] == "[QS-7] Fix login"
    assert payload["payload"]["source_url"].endswith("/browse/QS-7")
    assert payload["payload"]["jira_project_key"] == "QS"
    assert "status=In Progress" in payload["payload"]["summary"]

    assert build_issue_connector_payload({}, site="s", jira_project_key="QS") is None


def test_fetch_jira_issues_parses_search_response() -> None:
    def fetcher(url: str, headers: Mapping[str, str]) -> bytes:
        assert "search/jql" in url
        assert "QS" in url
        assert headers["Authorization"].startswith("Basic ")
        return json.dumps({"issues": [_issue("QS-1"), _issue("QS-2")]}).encode()

    site, issues = fetch_jira_issues(
        ENVIRON, jira_key="QS", max_results=10, fetcher=fetcher
    )

    assert site.startswith("https://")
    assert [i["key"] for i in issues] == ["QS-1", "QS-2"]


async def test_ingest_is_idempotent_and_counts_issues() -> None:
    await _ensure_graph_tables()
    test_key = f"TQ{uuid4().hex[:4].upper()}"
    await _cleanup_test_key(test_key)
    try:
        payloads = [
            build_issue_connector_payload(
                _issue(f"{test_key}-{n}"),
                site="https://example-team.atlassian.net",
                jira_project_key=test_key,
            )
            for n in (1, 2)
        ]
        first = await ingest_issue_payloads(payloads)
        second = await ingest_issue_payloads(payloads)

        assert first == {"source_events_created": 2, "already_present": 0}
        assert second == {"source_events_created": 0, "already_present": 2}

        async with AsyncSessionLocal() as session:
            count = await jira_issue_count_for_keys(session, [test_key])
        assert count == 2
    finally:
        await _cleanup_test_key(test_key)


async def test_jira_sync_script_records_source_control_request_without_live_fetch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = f"jira-sync-script-{uuid4().hex[:8]}"
    await _ensure_source_control_tables()

    def fail_fetch(*args, **kwargs):
        raise AssertionError("compatibility script must not call Jira directly")

    monkeypatch.setattr(sync_jira_issues, "fetch_jira_issues", fail_fetch)
    try:
        args = sync_jira_issues._parse_args(
            [
                "--confirm-sync",
                sync_jira_issues.CONFIRM_SYNC_PHRASE,
                "--request-key",
                marker,
                "--jira-key",
                "QS",
                "--max-results",
                "7",
                "--allow-live-readonly-apis",
                "--acknowledge-live-readonly-risk",
                "PRIVATE_ACK_DO_NOT_RETURN",
            ]
        )
        rc = await sync_jira_issues._run(args)
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
            assert row.source_type == "jira"
            assert row.action_type == "sync"
            assert row.external_side_effect is False
            assert row.input_snapshot["input"]["legacy_script"] == (
                "scripts/sync_jira_issues.py"
            )
            assert row.input_snapshot["input"]["requested_jira_keys"] == ["QS"]
            assert row.input_snapshot["input"]["max_results"] == 7
            assert row.input_snapshot["input"]["live_readonly_requested"] is True
            assert row.input_snapshot["input"]["live_readonly_ack_supplied"] is True
    finally:
        await _cleanup_source_request(marker)
