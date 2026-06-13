#!/usr/bin/env python
"""Bootstrap and start the FounderOS local runtime with one command.

This script makes the local happy path "run one command and it works":

1. Bootstrap the gitignored ``.local/`` workspace and ``.env.local`` managed
   block (idempotent; existing local secrets are preserved).
2. Run ``alembic upgrade head`` against the configured local database.
3. Start uvicorn on ``127.0.0.1:8765`` and print where to open the UI and
   where the Obsidian vault lives.

If the port is already taken the script prints a clear instruction and exits
without killing any process.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bootstrap_local_workspace import (  # noqa: E402
    VAULT_NAME,
    bootstrap_local_workspace,
)

HOST = "127.0.0.1"
PORT = 8765
UI_URL = f"http://{HOST}:{PORT}/ui"
VAULT_RELATIVE = f".local/obsidian/{VAULT_NAME}"


def port_in_use(host: str = HOST, port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def build_alembic_command() -> list[str]:
    return ["uv", "run", "alembic", "upgrade", "head"]


def build_uvicorn_command(host: str = HOST, port: int = PORT) -> list[str]:
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
        f"Port {port} is already in use. FounderOS may already be running — "
        f"open http://{host}:{port}/ui\n"
        f"To inspect the process: lsof -nP -iTCP:{port} -sTCP:LISTEN\n"
        "FounderOS did not stop any process."
    )


def _print_ready(workspace: Path) -> None:
    try:
        workspace_label = str(workspace.relative_to(ROOT))
    except ValueError:
        workspace_label = str(workspace)
    print("FounderOS local runtime is ready.", flush=True)
    print(f"  Open UI:        {UI_URL}", flush=True)
    print(f"  Obsidian vault: {VAULT_RELATIVE}", flush=True)
    print(f"  Workspace:      {workspace_label}", flush=True)
    print(
        "  In the UI: Knowledge tree -> Dry Run -> Sync Now -> Open Vault in Obsidian",
        flush=True,
    )


def main() -> int:
    result = bootstrap_local_workspace(repo_root=ROOT, apply=True)
    if port_in_use(HOST, PORT):
        print(occupied_port_message(HOST, PORT), file=sys.stderr, flush=True)
        return 2
    alembic = subprocess.run(build_alembic_command(), cwd=ROOT)
    if alembic.returncode != 0:
        return alembic.returncode
    _print_ready(Path(result["workspace_path"]))
    return subprocess.run(build_uvicorn_command(HOST, PORT), cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
