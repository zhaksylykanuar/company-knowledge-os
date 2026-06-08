from pathlib import Path
from typing import Any

import pytest

from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_ALLOWED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    UNKNOWN_PROVIDER,
    UNKNOWN_PROVIDER_BOUNDARY,
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

PROVIDER_BOUNDARY_INVENTORY = {
    "app/services/telegram_delivery.py::send_telegram_plain_text": "guarded_live_boundary",
    "app/connectors/gmail.py::get_gmail_service": "guarded_live_boundary",
    "app/connectors/gmail.py::list_messages": "guarded_live_boundary",
    "app/connectors/gmail.py::get_message": "guarded_live_boundary",
    "app/connectors/google_drive.py::get_drive_service": "guarded_live_boundary",
    "app/connectors/google_drive.py::list_ai_inbox_files": "guarded_live_boundary",
    "app/connectors/google_drive.py::download_file_text": "guarded_live_boundary",
    "app/connectors/github.py::list_repository_events": "guarded_live_boundary",
    "app/connectors/github.py::fetch_issue_events": "guarded_live_boundary",
    "app/connectors/github.py::fetch_pull_request_events": "guarded_live_boundary",
    "app/connectors/jira.py::search_issue_events": "guarded_live_boundary",
    "app/connectors/jira.py::fetch_project_issue_events": "guarded_live_boundary",
    "app/agents/llm_runner.py::get_openai_client": "guarded_live_boundary",
    "app/agents/llm_runner.py::LLMAgentRunner.extract": "guarded_live_boundary",
    "app/services/attention_triage.py::OpenAIAttentionTriageProvider": (
        "injected_client_only"
    ),
}

GUARDED_LIVE_PROVIDER_FILES = {
    "app/agents/llm_runner.py",
    "app/connectors/github.py",
    "app/connectors/gmail.py",
    "app/connectors/google_drive.py",
    "app/connectors/jira.py",
    "app/services/telegram_delivery.py",
}


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


def test_provider_execution_guard_sanitizes_unknown_labels() -> None:
    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        require_live_provider_execution_ack(
            provider="unsafe provider label",
            boundary="unsafe boundary label",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics["provider"] == UNKNOWN_PROVIDER
    assert diagnostics["boundary"] == UNKNOWN_PROVIDER_BOUNDARY
    assert "unsafe provider label" not in repr(diagnostics)
    assert "unsafe boundary label" not in repr(diagnostics)


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


def test_provider_execution_guard_knows_github_and_jira_boundaries() -> None:
    for provider, boundary in (
        ("github", "github_issue_events"),
        ("jira", "jira_issue_events"),
    ):
        diagnostics = require_live_provider_execution_ack(
            provider=provider,
            boundary=boundary,
            allow_live_provider_execution=True,
            provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
        )

        assert diagnostics.provider == provider
        assert diagnostics.boundary == boundary
        assert diagnostics.reason_code == PROVIDER_EXECUTION_ALLOWED


def test_provider_boundary_inventory_uses_safe_categories_only() -> None:
    assert set(PROVIDER_BOUNDARY_INVENTORY.values()) <= {
        "guarded_live_boundary",
        "injected_client_only",
    }
    assert all("://" not in boundary for boundary in PROVIDER_BOUNDARY_INVENTORY)


def test_known_live_provider_files_use_shared_guard() -> None:
    for relative_path in GUARDED_LIVE_PROVIDER_FILES:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "require_live_provider_execution_ack" in source


def test_gmail_connector_default_denies_before_provider_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.connectors import gmail

    build_called = False

    def forbidden_build(*args: Any, **kwargs: Any) -> Any:
        nonlocal build_called
        build_called = True
        raise AssertionError("default-denied Gmail boundary must not build a service")

    monkeypatch.setattr(gmail, "build", forbidden_build)

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        gmail.list_messages()

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert build_called is False


def test_gmail_connector_requires_exact_live_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.connectors import gmail

    monkeypatch.setattr(
        gmail,
        "build",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("missing Gmail ack must not build a service")
        ),
    )

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        gmail.get_message(
            "synthetic_message",
            allow_live_provider_execution=True,
            provider_execution_ack="wrong_ack",
        )

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_ACK_REQUIRED


def test_gmail_connector_allows_explicit_ack_with_synthetic_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.connectors import gmail

    class FakePath:
        def __init__(self, value: str) -> None:
            self.value = value

        def exists(self) -> bool:
            return True

    class FakeCreds:
        valid = True

    class FakeMessages:
        def list(self, **kwargs: Any) -> "FakeMessages":
            return self

        def execute(self) -> dict[str, Any]:
            return {"messages": [{"id": "synthetic_message"}]}

    class FakeUsers:
        def messages(self) -> FakeMessages:
            return FakeMessages()

    class FakeService:
        def users(self) -> FakeUsers:
            return FakeUsers()

    monkeypatch.setattr(gmail, "Path", FakePath)
    monkeypatch.setattr(
        gmail.Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *args, **kwargs: FakeCreds()),
    )
    monkeypatch.setattr(gmail, "build", lambda *args, **kwargs: FakeService())

    messages = gmail.list_messages(
        query="synthetic_query",
        max_results=1,
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )

    assert messages == [{"id": "synthetic_message"}]


def test_drive_connector_default_denies_before_provider_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.connectors import google_drive

    build_called = False

    def forbidden_build(*args: Any, **kwargs: Any) -> Any:
        nonlocal build_called
        build_called = True
        raise AssertionError("default-denied Drive boundary must not build a service")

    monkeypatch.setattr(google_drive.settings, "google_drive_ai_inbox_folder_id", "synthetic")
    monkeypatch.setattr(google_drive, "build", forbidden_build)

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        google_drive.list_ai_inbox_files(page_size=1)

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert build_called is False


def test_drive_connector_requires_exact_live_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.connectors import google_drive

    monkeypatch.setattr(google_drive.settings, "google_drive_ai_inbox_folder_id", "synthetic")
    monkeypatch.setattr(
        google_drive,
        "build",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("missing Drive ack must not build a service")
        ),
    )

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        google_drive.list_ai_inbox_files(
            page_size=1,
            allow_live_provider_execution=True,
            provider_execution_ack="wrong_ack",
        )

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_ACK_REQUIRED


def test_drive_connector_allows_explicit_ack_with_synthetic_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.connectors import google_drive

    class FakePath:
        def __init__(self, value: str) -> None:
            self.value = value

        def exists(self) -> bool:
            return True

    class FakeCreds:
        valid = True

    class FakeFiles:
        def list(self, **kwargs: Any) -> "FakeFiles":
            return self

        def execute(self) -> dict[str, Any]:
            return {"files": [{"id": "synthetic_file"}]}

    class FakeService:
        def files(self) -> FakeFiles:
            return FakeFiles()

    monkeypatch.setattr(google_drive.settings, "google_drive_ai_inbox_folder_id", "synthetic")
    monkeypatch.setattr(google_drive, "Path", FakePath)
    monkeypatch.setattr(
        google_drive.Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *args, **kwargs: FakeCreds()),
    )
    monkeypatch.setattr(google_drive, "build", lambda *args, **kwargs: FakeService())

    files = google_drive.list_ai_inbox_files(
        page_size=1,
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )

    assert files == [{"id": "synthetic_file"}]


def test_openai_client_factory_default_denies_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents import llm_runner

    client_created = False

    class ForbiddenOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            nonlocal client_created
            client_created = True
            raise AssertionError("default-denied OpenAI boundary must not create a client")

    monkeypatch.setattr(llm_runner, "OpenAI", ForbiddenOpenAI)

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        llm_runner.get_openai_client()

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert client_created is False


def test_openai_client_factory_requires_exact_live_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents import llm_runner

    monkeypatch.setattr(
        llm_runner,
        "OpenAI",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("missing OpenAI ack must not create a client")
        ),
    )

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        llm_runner.get_openai_client(
            allow_live_provider_execution=True,
            provider_execution_ack="wrong_ack",
        )

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_ACK_REQUIRED


def test_openai_client_factory_allows_explicit_ack_with_synthetic_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents import llm_runner

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = dict(kwargs)

    monkeypatch.setattr(llm_runner.settings, "enable_llm", True)
    monkeypatch.setattr(llm_runner.settings, "openai_api_key", "synthetic_key")
    monkeypatch.setattr(llm_runner, "OpenAI", FakeOpenAI)

    client = llm_runner.get_openai_client(
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )

    assert isinstance(client, FakeOpenAI)
