#!/usr/bin/env python
"""FounderOS local runtime command.

With no subcommand, this starts the complete local product: loopback Postgres
reuse/Compose fallback, verified pre-migration backup when needed, Alembic,
FastAPI, Next.js with its proxy configured, health readiness, and graceful
shutdown. Supporting doctor/backup/stop/smoke subcommands are read-only or
bounded to the gitignored local workspace.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bootstrap_local_workspace import (  # noqa: E402
    LocalWorkspaceBootstrapError,
    bootstrap_local_workspace,
)
from scripts.local_runtime import (  # noqa: E402
    BACKEND_BASE_URL,
    BACKEND_HOST,
    BACKEND_PORT,
    LocalRuntimeError,
    backend_command,
    collect_doctor_checks,
    create_local_backup,
    local_smoke,
    print_doctor_checks,
    run_backend_only,
    stop_recorded_runtime,
    supervise_local_runtime,
    tcp_port_in_use,
)

# Compatibility exports retained for the existing bootstrap tests and any
# operator tooling that imported the original helpers.
HOST = BACKEND_HOST
PORT = BACKEND_PORT
APP_URL = f"{BACKEND_BASE_URL}/"


def port_in_use(host: str = HOST, port: int = PORT) -> bool:
    return tcp_port_in_use(host, port)


def build_alembic_command() -> list[str]:
    return ["uv", "run", "alembic", "upgrade", "head"]


def build_uvicorn_command(host: str = HOST, port: int = PORT) -> list[str]:
    if host == HOST and port == PORT:
        return backend_command()
    return [
        "uv",
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def occupied_port_message(host: str = HOST, port: int = PORT) -> str:
    return (
        f"Port {port} is already in use. FounderOS did not stop any process.\n"
        f"Inspect it with: lsof -nP -iTCP:{port} -sTCP:LISTEN"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="start the complete local product")
    run_parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not open a browser or create an automatic one-time founder invite",
    )
    subparsers.add_parser("backend", help="run only the migration-safe local backend")
    subparsers.add_parser("doctor", help="inspect local readiness without changing services")
    subparsers.add_parser("backup", help="create and verify a loopback PostgreSQL backup")
    subparsers.add_parser("stop", help="gracefully stop the recorded local runtime")
    subparsers.add_parser("smoke", help="run read-only backend and web health checks")
    return parser


def _normalized_argv(argv: list[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0].startswith("-"):
        return ["run", *values]
    return values


def _settings() -> Any:
    # Settings env files are relative to the repository root. Never print the
    # model: it can contain credentials. Import only after chdir/bootstrap so
    # app modules used later by founder setup share the same resolved settings.
    os.chdir(ROOT)
    from app.core.config import Settings

    return Settings()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(_normalized_argv(argv))
    try:
        if args.command == "stop":
            return 0 if stop_recorded_runtime(ROOT) else 1
        if args.command == "smoke":
            return 0 if local_smoke() else 1
        if args.command == "doctor":
            return 0 if print_doctor_checks(collect_doctor_checks(ROOT, _settings())) else 1
        if args.command == "backup":
            create_local_backup(ROOT, _settings())
            return 0
        if args.command == "backend":
            bootstrap_local_workspace(repo_root=ROOT, apply=True)
            return run_backend_only(ROOT, _settings())
        if args.command == "run":
            bootstrap_local_workspace(repo_root=ROOT, apply=True)
            return supervise_local_runtime(ROOT, _settings(), no_open=bool(args.no_open))
        raise LocalRuntimeError("Unknown local runtime command.")
    except (LocalRuntimeError, LocalWorkspaceBootstrapError) as exc:
        print(f"FounderOS local runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
