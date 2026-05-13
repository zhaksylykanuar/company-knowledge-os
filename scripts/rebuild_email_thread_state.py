#!/usr/bin/env python
"""Rebuild deterministic email thread state from stored Gmail rows.

The command prints safe aggregate metadata only. It does not call Gmail or any
external API, and it does not print subjects, addresses, snippets, provider IDs,
raw refs, or message content.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_ENV_FILE = REPO_ROOT / ".env.operator"


def _load_operator_env_file() -> None:
    if not OPERATOR_ENV_FILE.exists():
        return

    for raw_line in OPERATOR_ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        try:
            tokens = shlex.split(raw_line, comments=True, posix=True)
        except ValueError:
            continue

        if not tokens:
            continue
        if tokens[0] == "export":
            tokens = tokens[1:]
        if len(tokens) != 1 or "=" not in tokens[0]:
            continue

        key, value = tokens[0].split("=", 1)
        os.environ.setdefault(key, value)


async def _run() -> dict:
    from app.services.email_threads import rebuild_email_thread_states_from_stored_gmail

    try:
        result = await rebuild_email_thread_states_from_stored_gmail()
    except Exception:
        return {
            "status": "blocked",
            "error_code": "email_thread_state_rebuild_blocked",
            "thread_states_built": 0,
            "messages_considered": 0,
            "status_counts": {},
            "private_content_printed": False,
        }

    return {
        "status": "completed",
        "thread_states_built": result.thread_states_built,
        "messages_considered": result.messages_considered,
        "status_counts": result.status_counts,
        "private_content_printed": False,
    }


def main() -> int:
    _load_operator_env_file()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    result = asyncio.run(_run())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
