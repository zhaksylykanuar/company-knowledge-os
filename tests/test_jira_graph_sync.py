from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.db.models import IngestedEvent
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
from tests.test_entity_resolution import _ensure_graph_tables, _seed

ENVIRON = {
    "FOS_JIRA_READONLY_SITE": "example-team.atlassian.net",
    "FOS_JIRA_READONLY_USER": "reader@example.invalid",
    "FOS_JIRA_READONLY_TOKEN": "test-token-not-real",
}


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
