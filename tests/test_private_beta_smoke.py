from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

from scripts import smoke_private_beta
from scripts.smoke_private_beta import SmokeConfig, SmokeConfigError, run_smoke

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_private_beta_smoke_calls_only_safe_endpoints_and_never_prints_key() -> None:
    requests: list[Request] = []
    emitted: list[str] = []
    secret_key = "test-smoke-secret-value"

    def opener(request: Request, *, timeout: float) -> FakeResponse:
        assert timeout == 3
        requests.append(request)
        path = request.selector.casefold()
        if path == "/api/v1/workspaces":
            return FakeResponse(401)
        return FakeResponse(200)

    config = SmokeConfig(
        api_base_url="https://backend.example.test",
        api_key=secret_key,
        owner_email="founder@example.test",
        workspace_id="00000000-0000-0000-0000-000000000001",
        timeout_seconds=3,
    )

    run_smoke(config, opener=opener, emit=emitted.append)

    called_paths = [request.selector for request in requests]
    assert called_paths == [
        "/health",
        "/api/v1/workspaces",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001?owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/github/connection-status?owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/company-brain?owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/github/operational-work?state=open&limit=25&owner_email=founder%40example.test",
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/briefings/manual?owner_email=founder%40example.test",
    ]
    for path in called_paths:
        lowered = path.casefold()
        assert not any(marker in lowered for marker in smoke_private_beta.FORBIDDEN_PATH_MARKERS)
    assert secret_key not in "\n".join(emitted)
    assert all("PASS" in line for line in emitted)


def test_private_beta_smoke_rejects_forbidden_paths_before_request() -> None:
    config = SmokeConfig(
        api_base_url="https://backend.example.test",
        api_key="test-smoke-key",
        owner_email="founder@example.test",
        workspace_id="00000000-0000-0000-0000-000000000001",
    )
    forbidden = smoke_private_beta.SmokeStep(
        name="forbidden",
        method="POST",
        path="/api/v1/workspaces/{workspace_id}/actions/proposals/proposal-id/execute",
    )

    with pytest.raises(SmokeConfigError, match="forbidden"):
        smoke_private_beta._build_request(forbidden, config)


def test_private_beta_smoke_requires_api_key_for_workspace_checks() -> None:
    config = SmokeConfig(
        api_base_url="https://backend.example.test",
        api_key=None,
        owner_email="founder@example.test",
        workspace_id="00000000-0000-0000-0000-000000000001",
        expect_auth_enabled=False,
    )

    with pytest.raises(SmokeConfigError, match="API key"):
        run_smoke(config, opener=lambda *_args, **_kwargs: FakeResponse(200), emit=lambda _line: None)


def test_private_beta_smoke_briefing_payload_is_deterministic_and_local_only() -> None:
    briefing = next(
        step
        for step in smoke_private_beta.WORKSPACE_STEPS
        if step.name == "deterministic briefing generation"
    )

    assert briefing.method == "POST"
    assert briefing.path.endswith("/briefings/manual")
    blob = json.dumps(briefing.body, sort_keys=True)
    for forbidden in ("execute", "sync-execution-result", "repositories/issues/sync"):
        assert forbidden not in blob


def test_private_beta_env_names_are_documented() -> None:
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
        "FOUNDEROS_SMOKE_OWNER_EMAIL",
        "FOUNDEROS_SMOKE_WORKSPACE_ID",
        "NEXT_PUBLIC_API_BASE_URL",
    ):
        assert name in combined


def test_env_example_values_remain_placeholders() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assignments = [
        line
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    ]

    assert assignments
    for line in assignments:
        _key, value = line.split("=", 1)
        assert value.startswith("<") and value.endswith(">")
