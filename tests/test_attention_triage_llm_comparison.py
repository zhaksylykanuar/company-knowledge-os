from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.attention_triage import (
    AttentionTriageResult,
    MockAttentionTriageProvider,
)
from app.services.provider_execution_guard import LIVE_PROVIDER_EXECUTION_ACK
from scripts import compare_attention_triage_llm_vs_deterministic as comparison


START_AT = datetime(2026, 1, 1, 9, tzinfo=UTC)
END_AT = START_AT + timedelta(hours=1)


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _session_factory() -> _FakeSession:
    return _FakeSession()


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "app_env": "local",
        "environment": "local",
        "debug": False,
        "attention_triage_enabled": True,
        "enable_llm": True,
        "openai_api_key": "configured",
        "attention_triage_model": "test-model",
        "attention_triage_max_text_chars": 1000,
        "attention_triage_min_confidence_to_hide": 0.80,
        "attention_triage_review_threshold": 0.55,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _record(
    source_object_id: str,
    *,
    title: str = "PRIVATE TITLE SHOULD NOT APPEAR",
    safe_summary: str = "PRIVATE SUMMARY SHOULD NOT APPEAR",
    activity_type: str = "email.received",
    actor: str = "external",
) -> SimpleNamespace:
    return SimpleNamespace(
        source="gmail",
        source_object_id=source_object_id,
        activity_type=activity_type,
        title=title,
        actor=actor,
        activity_created_at=START_AT,
        created_at=START_AT,
        project="PRIVATE PROJECT SHOULD NOT APPEAR",
        safe_summary=safe_summary,
        related_people=["PRIVATE PERSON SHOULD NOT APPEAR"],
        related_jira_keys=["PRIVATE-123"],
        related_prs=["123"],
        related_files=["PRIVATE FILE SHOULD NOT APPEAR"],
        evidence_refs=[{"source_object_id": source_object_id}],
    )


def _result(
    attention_class: str,
    *,
    priority: str = "low",
    show_in_digest: bool = True,
    confidence: float = 0.95,
) -> AttentionTriageResult:
    return AttentionTriageResult(
        attention_class=attention_class,
        priority=priority,
        show_in_digest=show_in_digest,
        confidence=confidence,
        reason="test reason",
        recommended_action="review",
        owner=None,
        deadline=None,
        evidence=[],
    )


def test_compare_attention_triage_results_reports_divergence_counts() -> None:
    deterministic_results = [
        _result("review_optional"),
        _result("review_optional"),
        _result("no_action_required", show_in_digest=False),
    ]
    llm_results = [
        _result("requires_my_attention", priority="high"),
        _result("review_optional"),
        _result("review_optional", show_in_digest=True),
    ]

    report = comparison.compare_attention_triage_results(
        deterministic_results=deterministic_results,
        llm_results=llm_results,
    )

    assert report["total"] == 3
    assert report["deterministic_counts"]["by_attention_class"] == {
        "no_action_required": 1,
        "review_optional": 2,
    }
    assert report["llm_counts"]["by_attention_class"] == {
        "requires_my_attention": 1,
        "review_optional": 2,
    }
    assert report["divergence_type_counts"] == {
        "exact_match": 1,
        "llm_more_urgent_class": 1,
        "visibility_changed": 1,
    }


@pytest.mark.asyncio
async def test_build_report_is_read_only_and_aggregate_only(monkeypatch: pytest.MonkeyPatch) -> None:
    records = [
        _record("private-id-1"),
        _record("private-id-2", activity_type="github.pr_assigned"),
    ]

    async def latest_window(_session: object, *, lookback_hours: int) -> tuple[datetime, datetime]:
        assert lookback_hours == 24
        return START_AT, END_AT

    async def records_for_window(
        _session: object,
        *,
        start_at: datetime,
        end_at: datetime,
        max_items: int,
    ) -> list[SimpleNamespace]:
        assert start_at == START_AT
        assert end_at == END_AT
        assert max_items == 2
        return records

    monkeypatch.setattr(comparison, "_latest_window", latest_window)
    monkeypatch.setattr(comparison, "_records_for_window", records_for_window)
    llm_provider = MockAttentionTriageProvider(
        [
            _result("requires_my_attention", priority="high"),
            _result("review_optional"),
        ]
    )

    report = await comparison.build_attention_triage_comparison_report(
        comparison.AttentionTriageComparisonQuery(
            confirm_compare=comparison.CONFIRM_COMPARE_PHRASE,
            acknowledge_live_provider_risk=LIVE_PROVIDER_EXECUTION_ACK,
            max_items=2,
        ),
        session_factory=_session_factory,
        settings_override=_settings(),
        environ={"APP_ENV": "local"},
        llm_provider=llm_provider,
    )

    assert report["status"] == "completed"
    assert report["total"] == 2
    assert report["provider"]["openai_call_count"] == 0
    assert report["safety"] == {
        "read_only": True,
        "db_write_scope": "none",
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": False,
        "triage_write_invoked": False,
        "raw_storage_touched": False,
        "obsidian_touched": False,
        "delivery_invoked": False,
        "telegram_invoked": False,
        "slack_invoked": False,
        "scheduler_execution": "disabled",
        "provider_guard_used": True,
        "openai_invoked": False,
        "credential_values_exposed": False,
        "raw_content_printed": False,
        "item_details_included": False,
        "evidence_refs_included": False,
        "private_content_printed": False,
    }
    assert report["llm_counts"]["by_attention_class"] == {
        "requires_my_attention": 1,
        "review_optional": 1,
    }
    assert report["deterministic_counts"]["by_attention_class"] == {"review_optional": 2}
    assert report["divergence_type_counts"] == {
        "exact_match": 1,
        "llm_more_urgent_class": 1,
    }

    encoded = json.dumps(report, sort_keys=True)
    assert "PRIVATE" not in encoded
    assert "private-id" not in encoded
    assert "PRIVATE-123" not in encoded
    assert "source_object_id" not in encoded


def test_query_requires_exact_guard_acknowledgement() -> None:
    args = argparse.Namespace(
        start_at=None,
        end_at=None,
        lookback_hours=24,
        max_items=5,
        include_synthetic=False,
        confirm_compare=comparison.CONFIRM_COMPARE_PHRASE,
        acknowledge_live_provider_risk="wrong",
        format="json",
    )

    with pytest.raises(comparison.AttentionTriageComparisonInputError):
        comparison._query_from_args(args)


@pytest.mark.asyncio
async def test_report_is_blocked_when_llm_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def latest_window(_session: object, *, lookback_hours: int) -> tuple[datetime, datetime]:
        return START_AT, END_AT

    async def records_for_window(
        _session: object,
        *,
        start_at: datetime,
        end_at: datetime,
        max_items: int,
    ) -> list[SimpleNamespace]:
        return [_record("private-id-1")]

    monkeypatch.setattr(comparison, "_latest_window", latest_window)
    monkeypatch.setattr(comparison, "_records_for_window", records_for_window)

    with pytest.raises(comparison.AttentionTriageComparisonBlockedError) as exc:
        await comparison.build_attention_triage_comparison_report(
            comparison.AttentionTriageComparisonQuery(
                confirm_compare=comparison.CONFIRM_COMPARE_PHRASE,
                acknowledge_live_provider_risk=LIVE_PROVIDER_EXECUTION_ACK,
            ),
            session_factory=_session_factory,
            settings_override=_settings(enable_llm=False),
            environ={"APP_ENV": "local"},
            llm_provider=MockAttentionTriageProvider([_result("review_optional")]),
        )

    assert str(exc.value) == "llm_disabled"
