#!/usr/bin/env python3
"""Authenticated local session/workspace smoke without printing credentials.

Credentials are accepted only through environment variables. The script logs
in, verifies the same cookie twice, optionally reads the selected workspace,
and always attempts logout. It performs no provider call or external write.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from collections.abc import Callable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.smoke_local import (  # noqa: E402
    SMOKE_API_BASE_URL_ENV,
    SMOKE_TIMEOUT_SECONDS_ENV,
    SmokeCheckError,
    SmokeConfigError,
    _NoRedirectHandler,
    _validate_local_base_url,
)

SMOKE_LOGIN_EMAIL_ENV = "FOUNDEROS_SMOKE_LOGIN_EMAIL"
SMOKE_LOGIN_PASSWORD_ENV = "FOUNDEROS_SMOKE_LOGIN_PASSWORD"
SMOKE_WORKSPACE_ID_ENV = "FOUNDEROS_SMOKE_WORKSPACE_ID"


class Opener(Protocol):
    def open(self, request: Request, *, timeout: float) -> Any: ...


@dataclass(frozen=True)
class AuthenticatedSmokeConfig:
    api_base_url: str
    email: str
    password: str
    workspace_id: str | None
    timeout_seconds: float = 10.0
    include_workspace_reads: bool = False


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SmokeConfigError(f"{name} is required")
    return value


def _timeout_from_env() -> float:
    raw = os.environ.get(SMOKE_TIMEOUT_SECONDS_ENV, "").strip()
    if not raw:
        return 10.0
    try:
        value = float(raw)
    except ValueError as exc:
        raise SmokeConfigError(
            f"{SMOKE_TIMEOUT_SECONDS_ENV} must be a number"
        ) from exc
    if value <= 0:
        raise SmokeConfigError(f"{SMOKE_TIMEOUT_SECONDS_ENV} must be positive")
    return value


def config_from_env_and_args(
    argv: list[str] | None = None,
) -> AuthenticatedSmokeConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        action="store_true",
        help="Also verify bounded Company, Headquarters and connection reads.",
    )
    args = parser.parse_args(argv)

    workspace_id = os.environ.get(SMOKE_WORKSPACE_ID_ENV, "").strip() or None
    if args.workspace:
        if workspace_id is None:
            raise SmokeConfigError(f"{SMOKE_WORKSPACE_ID_ENV} is required")
        try:
            workspace_id = str(UUID(workspace_id))
        except ValueError as exc:
            raise SmokeConfigError(
                f"{SMOKE_WORKSPACE_ID_ENV} must be a UUID"
            ) from exc

    return AuthenticatedSmokeConfig(
        api_base_url=_validate_local_base_url(
            os.environ.get(
                SMOKE_API_BASE_URL_ENV,
                "http://127.0.0.1:3000",
            )
        ),
        email=_required_env(SMOKE_LOGIN_EMAIL_ENV),
        password=_required_env(SMOKE_LOGIN_PASSWORD_ENV),
        workspace_id=workspace_id,
        timeout_seconds=_timeout_from_env(),
        include_workspace_reads=args.workspace,
    )


def _request(
    config: AuthenticatedSmokeConfig,
    *,
    method: str,
    path: str,
    body: dict[str, str] | None = None,
) -> Request:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/json",
        "Origin": config.api_base_url,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    return Request(
        f"{config.api_base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )


def _status(
    opener: Opener,
    request: Request,
    *,
    timeout: float,
) -> int:
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except URLError as exc:
        raise SmokeCheckError(
            "authenticated smoke failed before an HTTP response"
        ) from exc


def _require_status(
    *,
    name: str,
    opener: Opener,
    request: Request,
    timeout: float,
    emit: Callable[[str], None],
) -> None:
    status_code = _status(opener, request, timeout=timeout)
    if status_code != 200:
        raise SmokeCheckError(f"{name}: expected HTTP 200, got HTTP {status_code}")
    emit(f"PASS {name}: HTTP 200")


def run_authenticated_smoke(
    config: AuthenticatedSmokeConfig,
    *,
    opener: Opener | None = None,
    emit: Callable[[str], None] = print,
) -> None:
    active_opener = opener or build_opener(
        _NoRedirectHandler(),
        HTTPCookieProcessor(CookieJar()),
    )
    logged_in = False
    try:
        _require_status(
            name="founder login",
            opener=active_opener,
            request=_request(
                config,
                method="POST",
                path="/api/v1/auth/login",
                body={"email": config.email, "password": config.password},
            ),
            timeout=config.timeout_seconds,
            emit=emit,
        )
        logged_in = True
        for sequence in (1, 2):
            _require_status(
                name=f"session persistence {sequence}",
                opener=active_opener,
                request=_request(
                    config,
                    method="GET",
                    path="/api/v1/auth/me",
                ),
                timeout=config.timeout_seconds,
                emit=emit,
            )

        if config.include_workspace_reads:
            workspace_id = config.workspace_id
            if workspace_id is None:
                raise SmokeConfigError("workspace smoke requires an exact workspace UUID")
            paths = (
                ("workspace read", f"/api/v1/workspaces/{workspace_id}"),
                (
                    "headquarters read",
                    f"/api/v1/workspaces/{workspace_id}/headquarters",
                ),
                (
                    "company brain read",
                    f"/api/v1/workspaces/{workspace_id}/company-brain",
                ),
                (
                    "provider connection state read",
                    f"/api/v1/workspaces/{workspace_id}/github/connection-status",
                ),
            )
            for name, path in paths:
                _require_status(
                    name=name,
                    opener=active_opener,
                    request=_request(config, method="GET", path=path),
                    timeout=config.timeout_seconds,
                    emit=emit,
                )
    finally:
        if logged_in:
            _require_status(
                name="session logout",
                opener=active_opener,
                request=_request(
                    config,
                    method="POST",
                    path="/api/v1/auth/logout",
                ),
                timeout=config.timeout_seconds,
                emit=emit,
            )


def main(argv: list[str] | None = None) -> int:
    try:
        config = config_from_env_and_args(argv)
        run_authenticated_smoke(config)
    except (SmokeConfigError, SmokeCheckError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("FounderOS authenticated smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
