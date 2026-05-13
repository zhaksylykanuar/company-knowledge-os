#!/usr/bin/env python
"""Preview email attention triage with safe aggregate output only.

The command reads stored EmailThreadState rows and classifies them with the
conservative fallback provider by default. It does not call external APIs and
does not write to the database.
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
    from app.db.base import AsyncSessionLocal
    from app.services.email_attention import classify_email_thread_states

    try:
        async with AsyncSessionLocal() as session:
            result = await classify_email_thread_states(session)
    except Exception:
        return {
            "status": "blocked",
            "error_code": "email_attention_preview_blocked",
            "threads_considered": 0,
            "attention_class_counts": {},
            "action_type_counts": {},
            "priority_counts": {},
            "show_in_digest_counts": {},
            "low_confidence_visible_count": 0,
            "private_content_printed": False,
        }

    return {
        "status": "completed",
        **result.to_safe_dict(),
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
