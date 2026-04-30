from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.api.drive as drive_api
import app.api.gmail as gmail_api
import app.api.google as google_api
from app.main import app

SAFE_GMAIL_QUERY = "label:founderos-test"
BROAD_GMAIL_QUERY = "in:inbox OR in:sent"
DRIVE_FOLDER_ID = "drive-folder-test"


def _set_auth(monkeypatch, *, enabled: bool, key: SecretStr | str | None) -> None:
    monkeypatch.setattr(google_api.settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(google_api.settings, "api_auth_key", key)
    monkeypatch.setattr(google_api.settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _set_google_backfill(
    monkeypatch,
    *,
    gmail_enabled: bool = False,
    gmail_query: str | None = None,
    drive_enabled: bool = False,
    folder_id: str | None = None,
) -> None:
    monkeypatch.setattr(google_api.settings, "google_gmail_backfill_enabled", gmail_enabled)
    monkeypatch.setattr(google_api.settings, "google_gmail_backfill_query", gmail_query)
    monkeypatch.setattr(google_api.settings, "google_drive_backfill_enabled", drive_enabled)
    monkeypatch.setattr(google_api.settings, "google_drive_ai_inbox_folder_id", folder_id)


def test_google_backfill_preflight_is_protected(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        missing = client.get("/v1/google/backfill/preflight")
        valid = client.get(
            "/v1/google/backfill/preflight",
            headers={"X-FounderOS-API-Key": "test-api-key"},
        )

    assert missing.status_code == 401
    assert "test-api-key" not in missing.text
    assert valid.status_code == 200


def test_default_state_reports_gmail_and_drive_disabled_without_connector_calls(
    monkeypatch,
) -> None:
    _set_google_backfill(monkeypatch)

    def fail_list_messages(*, query: str, max_results: int) -> list[dict]:
        raise AssertionError("preflight must not call Gmail connector path")

    def fail_list_ai_inbox_files(*, max_results: int) -> list[dict]:
        raise AssertionError("preflight must not call Drive connector path")

    monkeypatch.setattr(gmail_api, "list_messages", fail_list_messages)
    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_list_ai_inbox_files)

    with TestClient(app) as client:
        response = client.get("/v1/google/backfill/preflight")

    assert response.status_code == 200
    body = response.json()
    assert body["overall_ready"] is False
    assert body["gmail"] == {
        "enabled": False,
        "query_source": "none",
        "query_configured": False,
        "query_allowed": False,
        "max_results": gmail_api.GMAIL_BACKFILL_DEFAULT_MAX_RESULTS,
        "max_results_allowed": True,
        "ready": False,
        "blockers": [
            google_api.GMAIL_BLOCKER_DISABLED,
            google_api.GMAIL_BLOCKER_QUERY_MISSING,
        ],
    }
    assert body["drive"] == {
        "enabled": False,
        "folder_boundary_configured": False,
        "max_results": drive_api.DRIVE_BACKFILL_DEFAULT_MAX_RESULTS,
        "max_results_allowed": True,
        "ready": False,
        "blockers": [
            google_api.DRIVE_BLOCKER_DISABLED,
            google_api.DRIVE_BLOCKER_FOLDER_BOUNDARY_MISSING,
        ],
    }
    assert body["notes"] == [
        "preflight_only",
        "no_google_api_calls_made",
        "production_sync_not_implemented",
    ]


def test_enabled_gmail_missing_or_blank_query_reports_not_ready(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, gmail_enabled=True)

    with TestClient(app) as client:
        missing = client.get("/v1/google/backfill/preflight")
        blank = client.get("/v1/google/backfill/preflight", params={"gmail_query": "  "})

    assert missing.status_code == 200
    assert missing.json()["gmail"]["ready"] is False
    assert missing.json()["gmail"]["query_source"] == "none"
    assert missing.json()["gmail"]["blockers"] == [google_api.GMAIL_BLOCKER_QUERY_MISSING]

    assert blank.status_code == 200
    assert blank.json()["gmail"]["ready"] is False
    assert blank.json()["gmail"]["query_source"] == "request"
    assert blank.json()["gmail"]["blockers"] == [google_api.GMAIL_BLOCKER_QUERY_MISSING]


def test_enabled_gmail_broad_query_reports_not_ready_without_echoing_query(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, gmail_enabled=True)

    with TestClient(app) as client:
        response = client.get(
            "/v1/google/backfill/preflight",
            params={"gmail_query": BROAD_GMAIL_QUERY},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["gmail"]["ready"] is False
    assert body["gmail"]["query_source"] == "request"
    assert body["gmail"]["query_configured"] is True
    assert body["gmail"]["query_allowed"] is False
    assert body["gmail"]["blockers"] == [google_api.GMAIL_BLOCKER_QUERY_TOO_BROAD]
    assert BROAD_GMAIL_QUERY not in response.text


def test_enabled_gmail_safe_query_and_limit_reports_gmail_ready(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, gmail_enabled=True)

    with TestClient(app) as client:
        response = client.get(
            "/v1/google/backfill/preflight",
            params={"gmail_query": SAFE_GMAIL_QUERY, "gmail_max_results": 7},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["overall_ready"] is False
    assert body["gmail"]["ready"] is True
    assert body["gmail"]["enabled"] is True
    assert body["gmail"]["query_source"] == "request"
    assert body["gmail"]["query_configured"] is True
    assert body["gmail"]["query_allowed"] is True
    assert body["gmail"]["max_results"] == 7
    assert body["gmail"]["max_results_allowed"] is True
    assert body["gmail"]["blockers"] == []
    assert SAFE_GMAIL_QUERY not in response.text


def test_enabled_gmail_configured_safe_query_reports_config_source(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, gmail_enabled=True, gmail_query=SAFE_GMAIL_QUERY)

    with TestClient(app) as client:
        response = client.get("/v1/google/backfill/preflight")

    assert response.status_code == 200
    body = response.json()
    assert body["gmail"]["ready"] is True
    assert body["gmail"]["query_source"] == "config"
    assert SAFE_GMAIL_QUERY not in response.text


def test_gmail_invalid_max_results_are_rejected(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, gmail_enabled=True, gmail_query=SAFE_GMAIL_QUERY)

    with TestClient(app) as client:
        zero = client.get("/v1/google/backfill/preflight", params={"gmail_max_results": 0})
        negative = client.get("/v1/google/backfill/preflight", params={"gmail_max_results": -1})
        too_large = client.get(
            "/v1/google/backfill/preflight",
            params={"gmail_max_results": gmail_api.GMAIL_BACKFILL_MAX_RESULTS + 1},
        )

    assert zero.status_code == 422
    assert negative.status_code == 422
    assert too_large.status_code == 422


def test_enabled_drive_missing_or_blank_folder_boundary_reports_not_ready(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, drive_enabled=True)

    with TestClient(app) as client:
        missing = client.get("/v1/google/backfill/preflight")
        _set_google_backfill(monkeypatch, drive_enabled=True, folder_id="  ")
        blank = client.get("/v1/google/backfill/preflight")

    assert missing.status_code == 200
    assert missing.json()["drive"]["ready"] is False
    assert missing.json()["drive"]["blockers"] == [
        google_api.DRIVE_BLOCKER_FOLDER_BOUNDARY_MISSING
    ]
    assert blank.status_code == 200
    assert blank.json()["drive"]["ready"] is False
    assert blank.json()["drive"]["blockers"] == [google_api.DRIVE_BLOCKER_FOLDER_BOUNDARY_MISSING]


def test_enabled_drive_folder_boundary_and_limit_reports_drive_ready(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, drive_enabled=True, folder_id=DRIVE_FOLDER_ID)

    with TestClient(app) as client:
        response = client.get(
            "/v1/google/backfill/preflight",
            params={"drive_max_results": 7},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["overall_ready"] is False
    assert body["drive"]["ready"] is True
    assert body["drive"]["enabled"] is True
    assert body["drive"]["folder_boundary_configured"] is True
    assert body["drive"]["max_results"] == 7
    assert body["drive"]["max_results_allowed"] is True
    assert body["drive"]["blockers"] == []
    assert DRIVE_FOLDER_ID not in response.text


def test_drive_invalid_max_results_are_rejected(monkeypatch) -> None:
    _set_google_backfill(monkeypatch, drive_enabled=True, folder_id=DRIVE_FOLDER_ID)

    with TestClient(app) as client:
        zero = client.get("/v1/google/backfill/preflight", params={"drive_max_results": 0})
        negative = client.get("/v1/google/backfill/preflight", params={"drive_max_results": -1})
        too_large = client.get(
            "/v1/google/backfill/preflight",
            params={"drive_max_results": drive_api.DRIVE_BACKFILL_MAX_RESULTS + 1},
        )

    assert zero.status_code == 422
    assert negative.status_code == 422
    assert too_large.status_code == 422


def test_overall_ready_requires_gmail_and_drive_ready(monkeypatch) -> None:
    _set_google_backfill(
        monkeypatch,
        gmail_enabled=True,
        drive_enabled=True,
        folder_id=DRIVE_FOLDER_ID,
    )

    with TestClient(app) as client:
        gmail_only_blocked = client.get("/v1/google/backfill/preflight")
        both_ready = client.get(
            "/v1/google/backfill/preflight",
            params={"gmail_query": SAFE_GMAIL_QUERY},
        )

    assert gmail_only_blocked.status_code == 200
    assert gmail_only_blocked.json()["overall_ready"] is False
    assert both_ready.status_code == 200
    assert both_ready.json()["overall_ready"] is True


def test_response_does_not_echo_private_query_folder_or_token_like_values(monkeypatch) -> None:
    private_query = "from:private-person@example.com label:private-source"
    private_folder_id = "private-drive-folder-id"
    token_like_value = "token-value-that-must-not-be-returned"
    _set_google_backfill(
        monkeypatch,
        gmail_enabled=True,
        drive_enabled=True,
        folder_id=private_folder_id,
    )
    monkeypatch.setattr(google_api.settings, "google_token_file", token_like_value)
    monkeypatch.setattr(google_api.settings, "google_gmail_token_file", token_like_value)

    with TestClient(app) as client:
        response = client.get(
            "/v1/google/backfill/preflight",
            params={"gmail_query": private_query},
        )

    assert response.status_code == 200
    assert response.json()["overall_ready"] is True
    assert private_query not in response.text
    assert "private-person@example.com" not in response.text
    assert private_folder_id not in response.text
    assert token_like_value not in response.text
