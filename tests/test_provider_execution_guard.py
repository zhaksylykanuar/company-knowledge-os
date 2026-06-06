import pytest

from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_ALLOWED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)


def test_provider_execution_guard_default_denies_without_ack() -> None:
    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        require_live_provider_execution_ack(
            provider="telegram",
            boundary="telegram_send_message",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "provider": "telegram",
        "boundary": "telegram_send_message",
        "execution_mode": "live_provider",
        "reason_code": PROVIDER_EXECUTION_DEFAULT_DENIED,
        "allowed": False,
    }


def test_provider_execution_guard_requires_exact_operator_ack() -> None:
    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        require_live_provider_execution_ack(
            provider="telegram",
            boundary="telegram_send_message",
            allow_live_provider_execution=True,
            provider_execution_ack="wrong_ack",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics["reason_code"] == PROVIDER_EXECUTION_ACK_REQUIRED
    assert diagnostics["allowed"] is False
    assert LIVE_PROVIDER_EXECUTION_ACK not in repr(diagnostics)


def test_provider_execution_guard_allows_explicit_live_ack() -> None:
    diagnostics = require_live_provider_execution_ack(
        provider="telegram",
        boundary="telegram_send_message",
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )

    assert diagnostics.as_dict() == {
        "provider": "telegram",
        "boundary": "telegram_send_message",
        "execution_mode": "live_provider",
        "reason_code": PROVIDER_EXECUTION_ALLOWED,
        "allowed": True,
    }
