from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, resolved_cors_allowed_origins
from app.main import app


def test_cors_defaults_to_local_origins_only_in_local_env() -> None:
    local = Settings(app_env="local", cors_allowed_origins=None, _env_file=None)
    production = Settings(app_env="production", cors_allowed_origins=None, _env_file=None)

    assert resolved_cors_allowed_origins(local)
    assert resolved_cors_allowed_origins(production) == []
    assert "*" not in resolved_cors_allowed_origins(local)


def test_cors_accepts_explicit_origins_and_filters_wildcards() -> None:
    config = Settings(
        app_env="production",
        cors_allowed_origins="https://frontend.example.test, *, not-a-url, http://localhost:3000/",
        _env_file=None,
    )

    assert resolved_cors_allowed_origins(config) == [
        "https://frontend.example.test",
        "http://localhost:3000",
    ]


def test_cors_settings_aliases(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDEROS_CORS_ALLOWED_ORIGINS", "https://frontend.example.test")
    monkeypatch.setenv("FOUNDEROS_CORS_ALLOW_CREDENTIALS", "true")

    config = Settings(_env_file=None)

    assert config.cors_allowed_origins == "https://frontend.example.test"
    assert config.cors_allow_credentials is True


def test_app_cors_preflight_allows_local_frontend_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
