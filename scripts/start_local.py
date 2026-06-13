#!/usr/bin/env python
"""Bootstrap and start FounderOS local runtime."""

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


def port_in_use(host: str = "127.0.0.1", port: int = 8765) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> int:
    result = bootstrap_local_workspace(repo_root=ROOT, apply=True)
    if port_in_use("127.0.0.1", 8765):
        print(
            "Port 8765 is already in use. "
            "Run: lsof -nP -iTCP:8765 -sTCP:LISTEN",
            file=sys.stderr,
        )
        return 2
    alembic = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=ROOT)
    if alembic.returncode != 0:
        return alembic.returncode
    print("Open FounderOS: http://127.0.0.1:8765/ui")
    print(f"Obsidian vault: .local/obsidian/{VAULT_NAME}")
    print(f"Local workspace: {Path(result['workspace_path']).relative_to(ROOT)}")
    return subprocess.run(
        [
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
