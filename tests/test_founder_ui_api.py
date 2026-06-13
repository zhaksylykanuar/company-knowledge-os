import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.api.ui as ui_api
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.main import app


def _set_auth(monkeypatch, *, enabled: bool, key: SecretStr | str | None) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", key)
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _trap_founder_builders(monkeypatch, *, message: str) -> None:
    async def fail_builder(*args: object, **kwargs: object) -> str:
        raise AssertionError(message)

    monkeypatch.setattr(ui_api, "build_status_reply_text", fail_builder)
    monkeypatch.setattr(ui_api, "build_dev_reply_text", fail_builder)
    monkeypatch.setattr(ui_api, "build_founder_overview", fail_builder)


def test_ui_page_is_public_and_contains_no_data(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = client.get("/ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "FounderOS" in response.text
    assert "test-api-key" not in response.text


def test_ui_page_injects_configured_auth_header_name(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-Custom-Test-Header")

    with TestClient(app) as client:
        response = client.get("/ui")

    assert response.status_code == 200
    assert "X-Custom-Test-Header" in response.text
    assert "__FOS_API_HEADER_NAME__" not in response.text
    assert "test-api-key" not in response.text


def test_ui_contains_sources_and_data_quality_surfaces(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = client.get("/ui")

    assert response.status_code == 200
    for marker in (
        "Sources / Data Control",
        "Data Quality",
        "/v1/founder/sources",
        "/v1/founder/data-quality",
        "/v1/founder/source-runs",
        "loadSources",
        "loadDataQuality",
        "masked_connection",
        "Pending source requests",
        "Recent source runs",
        "sourceRunBadge",
        "openSourceRunDetail",
        "normalized_event_count",
        "run events",
    ):
        assert marker in response.text, marker
    assert "test-api-key" not in response.text


def test_root_redirects_to_ui_page(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_founder_overview_returns_read_model(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    captured: dict[str, object] = {}

    async def fake_overview(**kwargs: object) -> dict:
        captured.update(kwargs)
        return {"status": {"level": "green"}, "projects": []}

    monkeypatch.setattr(ui_api, "build_founder_overview", fake_overview)

    with TestClient(app) as client:
        response = client.get("/v1/founder/overview", params={"attention_limit": 7})

    assert response.status_code == 200
    assert response.json()["status"]["level"] == "green"
    assert captured == {"attention_limit": 7}


def test_founder_status_returns_builder_text(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    captured: dict[str, object] = {}

    async def fake_status(**kwargs: object) -> str:
        captured.update(kwargs)
        return "status text"

    monkeypatch.setattr(ui_api, "build_status_reply_text", fake_status)

    with TestClient(app) as client:
        response = client.get(
            "/v1/founder/status",
            params={"q": "Atlas", "window_hours": 72, "limit": 5},
        )

    assert response.status_code == 200
    assert response.text == "status text"
    assert captured == {"window_hours": 72, "limit": 5, "question_text": "Atlas"}


def test_founder_dev_returns_builder_text(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async def fake_dev(**kwargs: object) -> str:
        return "dev overview text"

    monkeypatch.setattr(ui_api, "build_dev_reply_text", fake_dev)

    with TestClient(app) as client:
        response = client.get("/v1/founder/dev")

    assert response.status_code == 200
    assert response.text == "dev overview text"


@pytest.mark.parametrize(
    "path",
    ["/v1/founder/overview", "/v1/founder/status", "/v1/founder/dev"],
)
def test_founder_views_reject_missing_key_before_builders(monkeypatch, path: str) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))
    _trap_founder_builders(
        monkeypatch,
        message="unauthenticated founder view must not reach read-model builders",
    )

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


def test_founder_status_rejects_out_of_range_window(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    _trap_founder_builders(
        monkeypatch,
        message="invalid window must not reach read-model builders",
    )

    with TestClient(app) as client:
        response = client.get("/v1/founder/status", params={"window_hours": 0})

    assert response.status_code == 422
