from pathlib import Path
from typing import Any

import pytest

from app.services.scheduler_execution_guard import (
    AUTOMATIC_DELIVERY,
    AUTOMATIC_DELIVERY_DISABLED,
    BACKGROUND_DISPATCH,
    BACKGROUND_DISPATCH_DISABLED,
    MANUAL_OPERATOR_EXECUTION,
    OUTBOX_DRAIN,
    OUTBOX_DRAIN_DISABLED,
    READ_ONLY_REVIEW_EXECUTION,
    RETRY_WORKER,
    RETRY_WORKER_DISABLED,
    SCHEDULER_EXECUTION,
    SCHEDULER_EXECUTION_DISABLED,
    SCHEDULER_EXECUTION_NOT_REQUESTED,
    SchedulerExecutionBlockedError,
    require_no_scheduler_execution,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEDULER_OUTBOX_BOUNDARY_INVENTORY = {
    "scripts/send_test_telegram_delivery_intention.py::execute_test_send": (
        "manual_bounded_send_guarded"
    ),
    "scripts/send_test_telegram_delivery_intention.py::_send_bounded_chunks": (
        "manual_bounded_send_guarded"
    ),
    "app/services/digest_delivery_drafts.py::create_digest_delivery_intention": (
        "durable_handoff_not_execution"
    ),
    "app/services/digest_delivery_drafts.py::get_digest_delivery_intention_telegram_plan": (
        "read_only_plan_not_execution"
    ),
    "app/services/digest_delivery_drafts.py::get_digest_delivery_intention_telegram_execution_preflight": (
        "read_only_preflight_not_execution"
    ),
    "app/services/digest_delivery_drafts.py::get_digest_delivery_intention_telegram_execution_gate": (
        "read_only_gate_not_execution"
    ),
    "scripts/review_digest_delivery_intention.py::build_review": (
        "read_only_review_not_execution"
    ),
    "scripts/report_digest_delivery_intention_send_status.py::build_send_status_report": (
        "read_only_status_not_execution"
    ),
}


def test_scheduler_execution_guard_allows_manual_operator_execution() -> None:
    diagnostics = require_no_scheduler_execution(
        boundary="test_telegram_delivery_execution",
        execution_source=MANUAL_OPERATOR_EXECUTION,
    )

    assert diagnostics.as_dict() == {
        "execution_source": MANUAL_OPERATOR_EXECUTION,
        "boundary": "test_telegram_delivery_execution",
        "reason_code": SCHEDULER_EXECUTION_NOT_REQUESTED,
        "allowed": True,
    }


def test_scheduler_execution_guard_allows_read_only_review_execution() -> None:
    diagnostics = require_no_scheduler_execution(
        boundary="delivery_intention_send_status_report",
        execution_source=READ_ONLY_REVIEW_EXECUTION,
    )

    assert diagnostics.allowed is True
    assert diagnostics.reason_code == SCHEDULER_EXECUTION_NOT_REQUESTED


@pytest.mark.parametrize(
    ("execution_source", "reason_code"),
    [
        (SCHEDULER_EXECUTION, SCHEDULER_EXECUTION_DISABLED),
        (OUTBOX_DRAIN, OUTBOX_DRAIN_DISABLED),
        (AUTOMATIC_DELIVERY, AUTOMATIC_DELIVERY_DISABLED),
        (BACKGROUND_DISPATCH, BACKGROUND_DISPATCH_DISABLED),
        (RETRY_WORKER, RETRY_WORKER_DISABLED),
    ],
)
def test_scheduler_execution_guard_default_disables_automatic_sources(
    execution_source: str,
    reason_code: str,
) -> None:
    with pytest.raises(SchedulerExecutionBlockedError) as exc_info:
        require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source=execution_source,
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "execution_source": execution_source,
        "boundary": "test_telegram_delivery_execution",
        "reason_code": reason_code,
        "allowed": False,
    }


def test_scheduler_execution_guard_sanitizes_unknown_execution_source() -> None:
    with pytest.raises(SchedulerExecutionBlockedError) as exc_info:
        require_no_scheduler_execution(
            boundary="test_telegram_delivery_execution",
            execution_source="unsafe unexpected mode with details",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "execution_source": SCHEDULER_EXECUTION,
        "boundary": "test_telegram_delivery_execution",
        "reason_code": SCHEDULER_EXECUTION_DISABLED,
        "allowed": False,
    }
    assert "unsafe unexpected mode" not in repr(diagnostics)


async def test_scheduler_source_blocks_bounded_send_before_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.telegram_delivery import TelegramDeliveryResult
    from scripts import send_test_telegram_delivery_intention as send_script

    send_called = False

    async def forbidden_send_telegram_plain_text(
        **kwargs: Any,
    ) -> TelegramDeliveryResult:
        nonlocal send_called
        send_called = True
        raise AssertionError("scheduler-disabled path must not send")

    monkeypatch.setattr(
        "app.services.telegram_delivery.send_telegram_plain_text",
        forbidden_send_telegram_plain_text,
    )

    with pytest.raises(SchedulerExecutionBlockedError) as exc_info:
        await send_script._send_bounded_chunks(
            bot_token="<set locally>",
            chat_id="TELEGRAM_CHAT_ID",
            chunks=["synthetic digest"],
            transport=None,
            execution_source=OUTBOX_DRAIN,
        )

    assert exc_info.value.reason_code == OUTBOX_DRAIN_DISABLED
    assert send_called is False


async def test_scheduler_source_blocks_execute_test_send_before_db_or_send() -> None:
    from scripts import send_test_telegram_delivery_intention as send_script

    session_factory_called = False

    def forbidden_session_factory() -> Any:
        nonlocal session_factory_called
        session_factory_called = True
        raise AssertionError("scheduler-disabled path must not open DB sessions")

    with pytest.raises(SchedulerExecutionBlockedError) as exc_info:
        await send_script.execute_test_send(
            send_script.SendQuery(
                delivery_intention_id="dint_synthetic",
                execution_attempt_id="attempt-synthetic",
                max_chunks=1,
                test_mode=True,
                confirm_send=send_script.CONFIRM_SEND_PHRASE,
            ),
            session_factory=forbidden_session_factory,
            execution_source=AUTOMATIC_DELIVERY,
        )

    assert exc_info.value.reason_code == AUTOMATIC_DELIVERY_DISABLED
    assert session_factory_called is False


def test_scheduler_outbox_boundary_inventory_uses_safe_categories_only() -> None:
    assert set(SCHEDULER_OUTBOX_BOUNDARY_INVENTORY.values()) <= {
        "manual_bounded_send_guarded",
        "durable_handoff_not_execution",
        "read_only_plan_not_execution",
        "read_only_preflight_not_execution",
        "read_only_gate_not_execution",
        "read_only_review_not_execution",
        "read_only_status_not_execution",
    }
    assert all("://" not in boundary for boundary in SCHEDULER_OUTBOX_BOUNDARY_INVENTORY)


def test_known_manual_send_entrypoint_uses_scheduler_guard() -> None:
    source = (
        REPO_ROOT / "scripts" / "send_test_telegram_delivery_intention.py"
    ).read_text(encoding="utf-8")

    assert "require_no_scheduler_execution" in source
    assert "MANUAL_OPERATOR_EXECUTION" in source


def test_scheduler_outbox_static_inventory_has_no_unguarded_execution_entrypoints() -> None:
    suspicious_terms = (
        "scheduler",
        "outbox",
        "worker",
        "drain",
        "dispatch",
        "automatic_delivery",
        "retry_worker",
    )
    ignored_paths = {
        "app/services/guarded_execution_contracts.py",
        "app/services/guarded_execution_audit.py",
            "app/services/external_connector_registry.py",
            "app/services/external_connector_config.py",
                "app/services/jira_operating_model.py",
                "app/services/jira_portfolio_mapping.py",
                "app/services/jira_creation_dry_run.py",
                "app/services/local_connector_env.py",
                "app/services/production_operation_guard.py",
                "app/connectors/jira.py",
            "app/services/repository_portfolio.py",
            "app/services/scheduler_execution_guard.py",
                "scripts/check_external_connectors_readonly.py",
                "scripts/check_jira_readonly_inventory.py",
                "scripts/plan_jira_creation_dry_run.py",
                "scripts/doctor_external_connector_config.py",
        "scripts/report_ignored_file_cleanup_plan.py",
        "scripts/report_guarded_execution_readiness.py",
    }
    candidates: list[str] = []

    for root in (REPO_ROOT / "app", REPO_ROOT / "scripts"):
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            relative_path = path.relative_to(REPO_ROOT).as_posix()
            if relative_path in ignored_paths:
                continue

            source = path.read_text(encoding="utf-8")
            haystack = f"{relative_path}\n{source}".casefold()
            if not any(term in haystack for term in suspicious_terms):
                continue
            if "require_no_scheduler_execution" in source:
                continue
            if "scheduler_invoked" in source or "outbox_record_created" in source:
                continue
            candidates.append(relative_path)

    assert candidates == []
