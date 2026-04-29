from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.auth import API_AUTH_FAILURE_DETAIL, require_api_key, settings
from app.main import app


PROTECTED_ROUTE_METHODS = {
    ("/v1/events", "POST"),
    ("/v1/drive/backfill", "POST"),
    ("/v1/gmail/backfill", "POST"),
    ("/v1/knowledge/ingest-text", "POST"),
    ("/v1/knowledge/ingest-text-process", "POST"),
    ("/v1/knowledge/score", "POST"),
    ("/v1/knowledge/search", "GET"),
    ("/v1/knowledge/ask", "POST"),
    ("/v1/knowledge/attention", "GET"),
    ("/v1/extraction/demo", "POST"),
    ("/v1/extraction/process-document", "POST"),
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


def test_current_protected_routes_use_existing_api_key_dependency() -> None:
    for path, method in PROTECTED_ROUTE_METHODS:
        assert require_api_key in _route_dependency_calls(path, method)


def test_health_route_does_not_use_api_key_dependency() -> None:
    assert require_api_key not in _route_dependency_calls("/health", "GET")
