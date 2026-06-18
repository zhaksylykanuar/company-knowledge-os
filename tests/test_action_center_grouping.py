from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.action_center import (
    GROUP_CLEANUP,
    GROUP_CRITICAL,
    GROUP_DECISION,
    GROUP_EVIDENCE,
    GROUP_LATER,
    GROUP_ORDER,
    _classify,
    _grouped,
    build_action_center,
)
from app.services.second_opinion import FINDING_EXECUTION_MISMATCH, upsert_finding


def _act(**kw):
    base = {
        "title": "t",
        "why_now": "w",
        "affected_entity": None,
        "evidence_count": 0,
        "severity": "low",
        "confidence": None,
        "source": "second_opinion",
        "action_type": "resolve_conflict",
        "cta": "c",
        "action_ref": {},
        "flags": [],
        "visibility": "founder",
    }
    base.update(kw)
    return base


# --- the classifier is deterministic and explainable --------------------


def test_blocked_high_severity_is_critical_now() -> None:
    group, reason = _classify(
        _act(severity="high", source="execution", action_type="unblock_task",
             flags=["blocked"])
    )
    assert group == GROUP_CRITICAL
    assert "заблокирована" in reason


def test_overdue_high_severity_is_critical_now() -> None:
    group, reason = _classify(
        _act(severity="high", source="execution",
             action_type="renegotiate_deadline", flags=["overdue"])
    )
    assert group == GROUP_CRITICAL
    assert "просроч" in reason


def test_high_severity_conflict_with_evidence_is_critical() -> None:
    group, reason = _classify(
        _act(severity="high", source="second_opinion", evidence_count=3)
    )
    assert group == GROUP_CRITICAL
    assert "evidence (3)" in reason


def test_data_availability_gap_waits_for_evidence() -> None:
    group, reason = _classify(
        _act(severity="low", source="data_availability",
             action_type="refresh_data")
    )
    assert group == GROUP_EVIDENCE
    assert "данных" in reason


def test_conclusion_without_evidence_waits() -> None:
    group, reason = _classify(
        _act(severity="medium", source="second_opinion", evidence_count=0)
    )
    assert group == GROUP_EVIDENCE
    assert "без привязанного evidence" in reason


def test_low_confidence_conclusion_waits() -> None:
    group, reason = _classify(
        _act(severity="medium", source="sales", action_type="reengage_account",
             evidence_count=2, confidence=0.3)
    )
    assert group == GROUP_EVIDENCE
    assert "0.30" in reason


def test_ownerless_task_needs_decision() -> None:
    group, reason = _classify(
        _act(severity="medium", source="execution", action_type="assign_owner",
             flags=["ownerless"])
    )
    assert group == GROUP_DECISION
    assert "владельца" in reason


def test_resolvable_conflict_with_evidence_needs_decision() -> None:
    group, reason = _classify(
        _act(severity="medium", source="second_opinion",
             action_type="resolve_conflict", evidence_count=2, confidence=0.8)
    )
    assert group == GROUP_DECISION
    assert "2 evidence" in reason


def test_gardener_proposal_is_cleanup() -> None:
    group, reason = _classify(
        _act(severity="low", source="graph_gardener",
             action_type="review_hygiene", evidence_count=1, confidence=0.6)
    )
    assert group == GROUP_CLEANUP
    assert "гигиен" in reason.lower()


def test_stale_task_is_cleanup() -> None:
    group, reason = _classify(
        _act(severity="medium", source="execution", action_type="refresh_task",
             flags=["stale"])
    )
    assert group == GROUP_CLEANUP


def test_quiet_low_signal_is_later() -> None:
    group, reason = _classify(
        _act(severity="low", source="second_opinion",
             action_type="resolve_conflict", evidence_count=2, confidence=0.9)
    )
    assert group == GROUP_LATER
    assert "severity low" in reason


def test_grouped_preserves_order_and_stamps_each_action() -> None:
    actions = [
        _act(severity="high", source="execution", action_type="unblock_task",
             flags=["blocked"]),
        _act(severity="low", source="graph_gardener",
             action_type="review_hygiene", evidence_count=1, confidence=0.6),
    ]
    groups = _grouped(actions)
    assert [g["key"] for g in groups] == list(GROUP_ORDER)
    # Every action is stamped in place with a group + an explanation.
    for action in actions:
        assert action["group"] in GROUP_ORDER
        assert action["group_reason"]
    # Group membership matches the stamped group.
    for group in groups:
        for action in group["actions"]:
            assert action["group"] == group["key"]


# --- the built read-model exposes groups + reasons ----------------------


async def test_build_action_center_groups_high_severity_finding() -> None:
    marker = uuid4().hex[:8]
    key = f"acg:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=key,
                entity_id=f"project:acg-{marker}",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary=f"grouping finding {marker}",
                severity="high",
                confidence=0.85,
                evidence_refs=[{"source_id": "x"}, {"source_id": "y"}],
            )
            await session.commit()
            center = await build_action_center(session, limit=1000)

        assert [g["key"] for g in center["groups"]] == list(GROUP_ORDER)
        assert "by_group" in center["counts"]
        mine = [a for a in center["actions"] if marker in str(a.get("title"))]
        assert mine, "seeded finding should surface as an action"
        action = mine[0]
        # High severity + evidence-backed conflict => critical now, explained.
        assert action["group"] == GROUP_CRITICAL
        assert action["group_reason"]
        assert action["visibility"] is not None
        # Sum of group counts equals number of displayed actions.
        assert sum(g["count"] for g in center["groups"]) == len(center["actions"])
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
            await session.commit()
