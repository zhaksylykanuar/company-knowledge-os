from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

from scripts import smoke_local
from scripts.smoke_authenticated import (
    AuthenticatedSmokeConfig,
    run_authenticated_smoke,
)
from scripts.smoke_local import SmokeConfig, SmokeConfigError, run_smoke

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeAuthenticatedOpener:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    def open(self, request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 3
        self.requests.append(request)
        return FakeResponse(200)


def test_local_smoke_calls_only_safe_endpoints_and_never_prints_key() -> None:
    requests: list[Request] = []
    emitted: list[str] = []
    secret_key = "test-smoke-secret-value"

    def opener(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 3
        requests.append(request)
        path = request.selector.casefold()
        if path == "/api/v1/auth/me":
            return FakeResponse(401)
        return FakeResponse(200)

    config = SmokeConfig(
        api_base_url="http://127.0.0.1:3000",
        api_key=secret_key,
        owner_email="founder@example.test",
        workspace_id="00000000-0000-0000-0000-000000000001",
        timeout_seconds=3,
    )

    run_smoke(config, opener=opener, emit=emitted.append)

    called_paths = [request.selector for request in requests]
    assert called_paths == [
        "/login",
        "/health",
        "/api/v1/auth/me",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001?owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/github/connection-status?owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/company-brain?owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/github/operational-work?state=open&limit=25&owner_email=founder%40example.test",
    ]
    assert {request.get_method() for request in requests} == {"GET"}
    for path in called_paths:
        lowered = path.casefold()
        assert not any(marker in lowered for marker in smoke_local.FORBIDDEN_PATH_MARKERS)
    assert secret_key not in "\n".join(emitted)
    assert all("PASS" in line for line in emitted)


def test_authenticated_smoke_splits_session_and_workspace_reads_without_leaks() -> None:
    opener = FakeAuthenticatedOpener()
    emitted: list[str] = []
    secret_password = "never-print-this-password"
    workspace_id = "00000000-0000-0000-0000-000000000001"
    config = AuthenticatedSmokeConfig(
        api_base_url="http://127.0.0.1:3000",
        email="founder@example.test",
        password=secret_password,
        workspace_id=workspace_id,
        timeout_seconds=3,
        include_workspace_reads=True,
    )

    run_authenticated_smoke(config, opener=opener, emit=emitted.append)

    called = [
        (request.get_method(), request.selector)
        for request in opener.requests
    ]
    assert called == [
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/auth/me"),
        ("GET", f"/api/v1/workspaces/{workspace_id}"),
        ("GET", f"/api/v1/workspaces/{workspace_id}/headquarters"),
        ("GET", f"/api/v1/workspaces/{workspace_id}/company-brain"),
        (
            "GET",
            f"/api/v1/workspaces/{workspace_id}/github/connection-status",
        ),
        ("POST", "/api/v1/auth/logout"),
    ]
    output = "\n".join(emitted)
    assert secret_password not in output
    assert "founder@example.test" not in output
    assert all(line.startswith("PASS ") for line in emitted)


def test_local_smoke_rejects_forbidden_paths_before_request() -> None:
    config = SmokeConfig(
        api_base_url="http://127.0.0.1:3000",
        api_key="test-smoke-key",
        owner_email="founder@example.test",
        workspace_id="00000000-0000-0000-0000-000000000001",
    )
    forbidden = smoke_local.SmokeStep(
        name="forbidden",
        method="POST",
        path="/api/v1/workspaces/{workspace_id}/actions/proposals/proposal-id/execute",
    )

    with pytest.raises(SmokeConfigError, match="forbidden"):
        smoke_local._build_request(forbidden, config)


def test_local_smoke_requires_api_key_for_workspace_checks() -> None:
    config = SmokeConfig(
        api_base_url="http://127.0.0.1:3000",
        api_key=None,
        owner_email="founder@example.test",
        workspace_id="00000000-0000-0000-0000-000000000001",
        expect_auth_enabled=False,
    )

    with pytest.raises(SmokeConfigError, match="API key"):
        run_smoke(config, opener=lambda *_args, **_kwargs: FakeResponse(200), emit=lambda _line: None)


def test_local_smoke_briefing_is_an_explicit_local_mutation_opt_in() -> None:
    briefing = next(
        step
        for step in smoke_local.OPTIONAL_LOCAL_MUTATION_STEPS
        if step.name == "deterministic briefing generation"
    )

    assert briefing.method == "POST"
    assert briefing.path.endswith("/briefings/manual")
    blob = json.dumps(briefing.body, sort_keys=True)
    for forbidden in ("execute", "sync-execution-result"):
        assert forbidden not in blob

    default_config = smoke_local.config_from_env_and_args(["--skip-workspace-checks"])
    opted_in_config = smoke_local.config_from_env_and_args(
        ["--skip-workspace-checks", "--include-briefing"]
    )
    assert default_config.include_briefing is False
    assert opted_in_config.include_briefing is True


def test_local_smoke_defaults_to_frontend_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOUNDEROS_SMOKE_API_BASE_URL", raising=False)

    config = smoke_local.config_from_env_and_args(["--skip-workspace-checks"])

    assert config.api_base_url == "http://127.0.0.1:3000"


@pytest.mark.parametrize(
    "base_url",
    [
        "https://localhost:3000",
        "http://localhost:3000",
        "http://[::1]:3000",
        "http://backend.example.test:3000",
        "http://user:password@127.0.0.1:3000",
        "http://127.0.0.1:3000/unexpected-path",
    ],
)
def test_local_smoke_refuses_non_loopback_or_credentialed_origins(
    base_url: str,
) -> None:
    with pytest.raises(SmokeConfigError, match="local smoke"):
        smoke_local.config_from_env_and_args(
            ["--api-base-url", base_url, "--skip-workspace-checks"]
        )


def test_local_smoke_never_follows_redirects_with_credentials() -> None:
    handler = smoke_local._NoRedirectHandler()
    original = Request(
        "http://127.0.0.1:3000/api/v1/workspaces/example",
        headers={"X-FounderOS-API-Key": "must-not-leave-loopback"},
    )

    redirected = handler.redirect_request(
        original,
        None,
        302,
        "Found",
        {"Location": "https://external.example.test/collect"},
        "https://external.example.test/collect",
    )

    assert redirected is None


def test_local_smoke_env_names_are_documented() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    web_readme = (ROOT / "web" / "README.md").read_text(encoding="utf-8")
    combined = "\n".join([readme, env_example, makefile, web_readme])

    for name in (
        "FOUNDEROS_CORS_ALLOWED_ORIGINS",
        "FOUNDEROS_SMOKE_API_BASE_URL",
        "FOUNDEROS_SMOKE_API_KEY",
        "FOUNDEROS_SMOKE_API_KEY_HEADER_NAME",
        "FOUNDEROS_SMOKE_LOGIN_EMAIL",
        "FOUNDEROS_SMOKE_LOGIN_PASSWORD",
        "FOUNDEROS_SMOKE_OWNER_EMAIL",
        "FOUNDEROS_SMOKE_WORKSPACE_ID",
        "FOUNDEROS_E2E_LOGIN_EMAIL",
        "FOUNDEROS_E2E_LOGIN_PASSWORD",
        "NEXT_PUBLIC_API_BASE_URL",
    ):
        assert name in combined

    for target in (
        "local-liveness-smoke",
        "local-session-smoke",
        "local-workspace-smoke",
        "local-browser-smoke",
    ):
        assert target in makefile


def test_env_example_values_remain_placeholders() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    safe_local_values = {"http://127.0.0.1:8765", "http://127.0.0.1:3000"}
    assignments = [
        line
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    ]

    assert assignments
    for line in assignments:
        _key, value = line.split("=", 1)
        is_placeholder = value.startswith("<") and value.endswith(">")
        assert is_placeholder or value in safe_local_values
