#!/usr/bin/env python3
"""Read-only FounderOS private-beta smoke checks.

The script reports only step names and HTTP status codes. It never prints API
keys, environment values, response bodies, or provider payloads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

SMOKE_API_BASE_URL_ENV = "FOUNDEROS_SMOKE_API_BASE_URL"
SMOKE_API_KEY_ENV = "FOUNDEROS_SMOKE_API_KEY"
SMOKE_API_KEY_HEADER_NAME_ENV = "FOUNDEROS_SMOKE_API_KEY_HEADER_NAME"
SMOKE_OWNER_EMAIL_ENV = "FOUNDEROS_SMOKE_OWNER_EMAIL"
SMOKE_WORKSPACE_ID_ENV = "FOUNDEROS_SMOKE_WORKSPACE_ID"
SMOKE_EXPECT_AUTH_ENV = "FOUNDEROS_SMOKE_EXPECT_AUTH"
SMOKE_TIMEOUT_SECONDS_ENV = "FOUNDEROS_SMOKE_TIMEOUT_SECONDS"
API_KEY_HEADER_NAME = "X-FounderOS-API-Key"

FORBIDDEN_PATH_MARKERS = (
    "/execute",
    "/repositories/issues/sync",
    "/repositories/pull-requests/sync",
    "/sync-execution-result",
    "/connections/provider-token",
    "/normalize-local",
    "/local-sync",
)


class SmokeConfigError(RuntimeError):
    pass


class SmokeCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmokeConfig:
    api_base_url: str
    api_key: str | None
    owner_email: str | None
    workspace_id: str | None
    api_key_header_name: str = API_KEY_HEADER_NAME
    timeout_seconds: float = 10.0
    expect_auth_enabled: bool = True
    skip_workspace_checks: bool = False
    include_briefing: bool = True


@dataclass(frozen=True)
class SmokeStep:
    name: str
    method: str
    path: str
    expected_statuses: tuple[int, ...] = (200,)
    include_api_key: bool = True
    include_owner_email: bool = True
    body: dict[str, Any] | None = None


WORKSPACE_STEPS = (
    SmokeStep(
        name="workspace read",
        method="GET",
        path="/api/v1/workspaces/{workspace_id}",
    ),
    SmokeStep(
        name="github connection status read",
        method="GET",
        path="/api/v1/workspaces/{workspace_id}/github/connection-status",
    ),
    SmokeStep(
        name="company brain read",
        method="GET",
        path="/api/v1/workspaces/{workspace_id}/company-brain",
    ),
    SmokeStep(
        name="operational work read",
        method="GET",
        path="/api/v1/workspaces/{workspace_id}/github/operational-work?state=open&limit=25",
    ),
    SmokeStep(
        name="deterministic briefing generation",
        method="POST",
        path="/api/v1/workspaces/{workspace_id}/briefings/manual",
        body={
            "focus": ["github", "sync", "repositories"],
            "include_github": True,
            "include_connections": True,
            "include_sync_jobs": True,
            "include_repository_inventory": True,
            "limit": 10,
        },
    ),
)


def _truthy(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _float_env(name: str, *, default: float) -> float:
    value = _env_value(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise SmokeConfigError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise SmokeConfigError(f"{name} must be positive")
    return parsed


def config_from_env_and_args(argv: list[str] | None = None) -> SmokeConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=_env_value(SMOKE_API_BASE_URL_ENV))
    parser.add_argument("--api-key", default=_env_value(SMOKE_API_KEY_ENV))
    parser.add_argument(
        "--api-key-header-name",
        default=_env_value(SMOKE_API_KEY_HEADER_NAME_ENV) or API_KEY_HEADER_NAME,
    )
    parser.add_argument("--owner-email", default=_env_value(SMOKE_OWNER_EMAIL_ENV))
    parser.add_argument("--workspace-id", default=_env_value(SMOKE_WORKSPACE_ID_ENV))
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=_float_env(SMOKE_TIMEOUT_SECONDS_ENV, default=10.0),
    )
    parser.add_argument(
        "--allow-auth-disabled",
        action="store_true",
        help="Do not require the protected auth probe to return 401.",
    )
    parser.add_argument(
        "--skip-workspace-checks",
        action="store_true",
        help="Run only health/auth probes; no workspace-scoped checks.",
    )
    parser.add_argument(
        "--skip-briefing",
        action="store_true",
        help="Skip deterministic manual briefing generation.",
    )
    args = parser.parse_args(argv)

    return SmokeConfig(
        api_base_url=(args.api_base_url or "http://127.0.0.1:8765").rstrip("/"),
        api_key=args.api_key,
        api_key_header_name=args.api_key_header_name,
        owner_email=args.owner_email,
        workspace_id=args.workspace_id,
        timeout_seconds=args.timeout_seconds,
        expect_auth_enabled=(
            _truthy(_env_value(SMOKE_EXPECT_AUTH_ENV), default=True)
            and not args.allow_auth_disabled
        ),
        skip_workspace_checks=args.skip_workspace_checks,
        include_briefing=not args.skip_briefing,
    )


def _safe_path(path: str) -> None:
    lowered = path.casefold()
    for marker in FORBIDDEN_PATH_MARKERS:
        if marker in lowered:
            raise SmokeConfigError("smoke path is forbidden by safety policy")


def _format_path(template: str, config: SmokeConfig) -> str:
    workspace_id = config.workspace_id or ""
    path = template.replace("{workspace_id}", workspace_id)
    _safe_path(path)
    return path


def _append_owner_email(path: str, config: SmokeConfig, *, include_owner_email: bool) -> str:
    if not include_owner_email or not config.owner_email:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode({'owner_email': config.owner_email})}"


def _build_request(step: SmokeStep, config: SmokeConfig) -> Request:
    method = step.method.upper()
    if method not in {"GET", "POST"}:
        raise SmokeConfigError("smoke method is forbidden by safety policy")
    path = _format_path(step.path, config)
    path = _append_owner_email(path, config, include_owner_email=step.include_owner_email)
    url = urljoin(f"{config.api_base_url}/", path.lstrip("/"))
    data = None
    headers = {"Accept": "application/json"}
    if step.include_api_key:
        if not config.api_key:
            raise SmokeConfigError("API key is required for protected smoke checks")
        header_name = config.api_key_header_name.strip() or API_KEY_HEADER_NAME
        headers[header_name] = config.api_key
    if step.body is not None:
        data = json.dumps(step.body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return Request(url, data=data, headers=headers, method=method)


def _request_status(
    step: SmokeStep,
    config: SmokeConfig,
    *,
    opener: Callable[..., Any] = urlopen,
) -> int:
    request = _build_request(step, config)
    try:
        with opener(request, timeout=config.timeout_seconds) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except URLError as exc:
        raise SmokeCheckError(f"{step.name}: request failed before HTTP response") from exc


def _run_step(
    step: SmokeStep,
    config: SmokeConfig,
    *,
    opener: Callable[..., Any],
    emit: Callable[[str], None],
) -> None:
    status = _request_status(step, config, opener=opener)
    if status not in step.expected_statuses:
        raise SmokeCheckError(f"{step.name}: expected configured status, got HTTP {status}")
    emit(f"PASS {step.name}: HTTP {status}")


def run_smoke(
    config: SmokeConfig,
    *,
    opener: Callable[..., Any] = urlopen,
    emit: Callable[[str], None] = print,
) -> None:
    _run_step(
        SmokeStep(
            name="health",
            method="GET",
            path="/health",
            include_api_key=False,
            include_owner_email=False,
        ),
        config,
        opener=opener,
        emit=emit,
    )

    if config.expect_auth_enabled:
        _run_step(
            SmokeStep(
                name="protected auth probe",
                method="GET",
                path="/api/v1/workspaces",
                expected_statuses=(401,),
                include_api_key=False,
                include_owner_email=False,
            ),
            config,
            opener=opener,
            emit=emit,
        )

    if config.skip_workspace_checks:
        emit("SKIP workspace checks")
        return

    if not config.owner_email:
        raise SmokeConfigError("owner email is required for workspace smoke checks")
    if not config.workspace_id:
        raise SmokeConfigError("workspace id is required for workspace smoke checks")

    steps = [step for step in WORKSPACE_STEPS if config.include_briefing or step.name != "deterministic briefing generation"]
    for step in steps:
        _run_step(step, config, opener=opener, emit=emit)


def main(argv: list[str] | None = None) -> int:
    try:
        config = config_from_env_and_args(argv)
        run_smoke(config)
    except (SmokeConfigError, SmokeCheckError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("FounderOS private-beta smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
