import builtins

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.api.drive as drive_api
import app.api.gmail as gmail_api
from app.api.auth import API_AUTH_FAILURE_DETAIL, require_api_key, settings
from app.main import app


PROTECTED_ROUTE_METHODS = {
    ("/v1/events", "POST"),
    ("/v1/drive/backfill", "POST"),
    ("/v1/gmail/backfill", "POST"),
    ("/v1/google/backfill/preflight", "GET"),
    ("/v1/knowledge/ingest-text", "POST"),
    ("/v1/knowledge/ingest-text-process", "POST"),
    ("/v1/knowledge/score", "POST"),
    ("/v1/knowledge/search", "GET"),
    ("/v1/knowledge/ask", "POST"),
    ("/v1/knowledge/attention", "GET"),
    ("/v1/extraction/demo", "POST"),
    ("/v1/extraction/process-document", "POST"),
    ("/v1/digest/source-activity", "GET"),
    ("/v1/digest/source-activity/text", "GET"),
    ("/v1/founder/overview", "GET"),
    ("/v1/founder/status", "GET"),
    ("/v1/founder/dev", "GET"),
    ("/v1/inbox", "GET"),
    ("/v1/inbox/proposals/{proposal_id}/decision", "POST"),
    ("/v1/founder/second-opinion", "GET"),
    ("/v1/founder/second-opinion/{finding_key:path}/trail", "GET"),
    ("/v1/founder/second-opinion/{finding_key:path}/status", "POST"),
    ("/v1/founder/second-opinion/{finding_key:path}/snooze", "POST"),
    ("/v1/founder/second-opinion/{finding_key:path}/note", "POST"),
    ("/v1/graph/tree", "GET"),
    ("/v1/knowledge/graph", "GET"),
    ("/v1/knowledge/nodes/{node_id:path}", "GET"),
    ("/v1/knowledge/export/obsidian-preview", "POST"),
    ("/v1/knowledge/obsidian/status", "GET"),
    ("/v1/knowledge/obsidian/sync", "POST"),
    ("/v1/knowledge/obsidian/open-vault", "GET"),
    ("/v1/knowledge/obsidian/open-node/{node_id:path}", "GET"),
    ("/v1/graph/links/{link_id:path}/review", "POST"),
    ("/v1/founder/data-availability", "GET"),
    ("/v1/founder/sources", "GET"),
    ("/v1/founder/sources/{source_type}/{action_type}", "POST"),
    ("/v1/founder/data-quality", "GET"),
    ("/v1/founder/source-runs", "GET"),
    ("/v1/founder/declarations/{key}", "GET"),
    ("/v1/founder/declarations/{key}", "PUT"),
    ("/v1/source-events", "GET"),
    ("/v1/source-events/{source_event_id}", "GET"),
    ("/v1/founder/command-center", "GET"),
    ("/v1/founder/agent-runs", "GET"),
    ("/v1/founder/sales-signals", "GET"),
    ("/v1/founder/execution", "GET"),
    ("/v1/founder/execution/tasks/{issue_key}", "GET"),
    ("/v1/founder/team-load", "GET"),
    ("/v1/founder/product", "GET"),
    ("/v1/founder/action-center", "GET"),
}


def _set_auth(monkeypatch, *, enabled: bool, key: SecretStr | str | None) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", key)
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _demo_payload() -> dict[str, str]:
    return {
        "text": "TODO prepare route auth review.",
        "source_document_id": "doc_route_auth",
        "chunk_id": "chunk_route_auth",
        "raw_object_ref": "raw://route-auth",
    }


def _post_demo(client: TestClient, *, key: str | None = None):
    headers = {"X-FounderOS-API-Key": key} if key is not None else None
    return client.post("/v1/extraction/demo", json=_demo_payload(), headers=headers)


def _route_dependency_calls(path: str, method: str) -> list[object]:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == path and method in route.methods:
            return [dependency.call for dependency in route.dependant.dependencies]
    raise AssertionError(f"route not found: {method} {path}")


def _trap_google_connector_paths(monkeypatch, *, message: str) -> None:
    def fail_connector_call(*args: object, **kwargs: object) -> None:
        raise AssertionError(message)

    monkeypatch.setattr(gmail_api, "list_messages", fail_connector_call)
    monkeypatch.setattr(gmail_api, "get_message", fail_connector_call)
    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_connector_call)
    monkeypatch.setattr(drive_api, "download_file_text", fail_connector_call)

    blocked_import_prefixes = (
        "app.connectors.gmail",
        "app.connectors.google_drive",
        "google_auth_oauthlib.flow",
        "googleapiclient.discovery",
    )
    real_import = builtins.__import__

    def fail_connector_import(
        name: str,
        globals: dict | None = None,
        locals: dict | None = None,
        fromlist: tuple | list = (),
        level: int = 0,
    ) -> object:
        if any(
            name == blocked or name.startswith(f"{blocked}.")
            for blocked in blocked_import_prefixes
        ):
            raise AssertionError(message)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_connector_import)


def test_health_remains_public_when_auth_enabled(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_route_reachable_when_auth_disabled(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    with TestClient(app) as client:
        response = _post_demo(client)

    assert response.status_code == 200
    assert response.json()["tasks"]


def test_protected_route_fails_closed_when_configured_key_missing(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=None)

    with TestClient(app) as client:
        response = _post_demo(client, key="test-api-key")

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


def test_protected_route_rejects_missing_request_key(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = _post_demo(client)

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


def test_protected_route_rejects_wrong_request_key_without_exposing_keys(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = _post_demo(client, key="wrong-test-key")

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text
    assert "wrong-test-key" not in response.text


def test_protected_route_accepts_valid_request_key(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = _post_demo(client, key="test-api-key")

    assert response.status_code == 200
    assert response.json()["tasks"]


def test_google_backfill_routes_reject_unauthenticated_before_connector_paths(
    monkeypatch,
) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))
    private_markers = [
        "PRIVATE_BACKFILL_AUTH_SECRET_MARKER",
        "PRIVATE_BACKFILL_AUTH_TOKEN_MARKER",
        "PRIVATE_BACKFILL_AUTH_PROVIDER_MARKER",
        "PRIVATE_BACKFILL_AUTH_QUERY_MARKER",
        "PRIVATE_BACKFILL_AUTH_BOUNDARY_MARKER",
        "PRIVATE_BACKFILL_AUTH_FILE_MARKER",
        "PRIVATE_BACKFILL_AUTH_LINK_MARKER",
        "PRIVATE_BACKFILL_AUTH_RAW_MARKER",
    ]
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_enabled", True)
    monkeypatch.setattr(
        gmail_api.settings,
        "google_gmail_backfill_query",
        private_markers[3],
    )
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", True)
    monkeypatch.setattr(
        drive_api.settings,
        "google_drive_ai_inbox_folder_id",
        private_markers[4],
    )
    _trap_google_connector_paths(
        monkeypatch,
        message="unauthenticated backfill must not reach Google connector paths",
    )

    with TestClient(app) as client:
        gmail_response = client.post(
            "/v1/gmail/backfill",
            params={
                "persist": "false",
                "max_results": 1,
                "query": private_markers[3],
            },
        )
        drive_response = client.post(
            "/v1/drive/backfill",
            params={"persist": "false", "max_results": 1},
        )

    for response in (gmail_response, drive_response):
        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in response.text
        for marker in private_markers:
            assert marker not in response.text


def test_google_backfill_routes_reject_authenticated_when_disabled_before_connector_paths(
    monkeypatch,
) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))
    private_markers = [
        "PRIVATE_DISABLED_SECRET_MARKER",
        "PRIVATE_DISABLED_TOKEN_MARKER",
        "PRIVATE_DISABLED_PROVIDER_MARKER",
        "PRIVATE_DISABLED_QUERY_MARKER",
        "PRIVATE_DISABLED_BOUNDARY_MARKER",
        "PRIVATE_DISABLED_FILE_MARKER",
        "PRIVATE_DISABLED_LINK_MARKER",
        "PRIVATE_DISABLED_RAW_MARKER",
    ]
    monkeypatch.setattr(gmail_api.settings, "google_client_secrets_file", private_markers[0])
    monkeypatch.setattr(gmail_api.settings, "google_gmail_token_file", private_markers[1])
    monkeypatch.setattr(drive_api.settings, "google_token_file", private_markers[1])
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_enabled", False)
    monkeypatch.setattr(
        gmail_api.settings,
        "google_gmail_backfill_query",
        private_markers[3],
    )
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", False)
    monkeypatch.setattr(
        drive_api.settings,
        "google_drive_ai_inbox_folder_id",
        private_markers[4],
    )
    _trap_google_connector_paths(
        monkeypatch,
        message="disabled backfill must not reach Google connector paths",
    )

    headers = {"X-FounderOS-API-Key": "test-api-key"}
    with TestClient(app) as client:
        gmail_response = client.post(
            "/v1/gmail/backfill",
            params={
                "persist": "false",
                "max_results": 1,
                "query": private_markers[3],
            },
            headers=headers,
        )
        drive_response = client.post(
            "/v1/drive/backfill",
            params={"persist": "false", "max_results": 1},
            headers=headers,
        )

    assert gmail_response.status_code == 403
    assert gmail_response.json() == {"detail": "Gmail backfill is disabled."}
    assert drive_response.status_code == 403
    assert drive_response.json() == {"detail": "Google Drive backfill is disabled."}
    for response in (gmail_response, drive_response):
        assert "test-api-key" not in response.text
        for marker in private_markers:
            assert marker not in response.text


def test_current_protected_routes_use_existing_api_key_dependency() -> None:
    for path, method in PROTECTED_ROUTE_METHODS:
        assert require_api_key in _route_dependency_calls(path, method)


def test_health_route_does_not_use_api_key_dependency() -> None:
    assert require_api_key not in _route_dependency_calls("/health", "GET")


def test_ui_page_route_does_not_use_api_key_dependency() -> None:
    assert require_api_key not in _route_dependency_calls("/ui", "GET")
