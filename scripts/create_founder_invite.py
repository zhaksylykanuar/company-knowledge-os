#!/usr/bin/env python
"""Create a one-time invite URL for safe founder enrollment.

The database stores only a SHA-256 digest.  The raw token appears only inside
the URL printed by this operator command, so the output must be handled like a
credential and must never be pasted into logs, docs, commits, or chat.

Usage:
  UV_NO_SYNC=1 uv run python scripts/create_founder_invite.py \
      --base-url https://founderos.example.com --ttl-hours 72
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.services.founder_enrollment_service import (  # noqa: E402
    DEFAULT_FOUNDER_INVITE_TTL_HOURS,
    MAX_FOUNDER_INVITE_TTL_HOURS,
    create_founder_invite,
)


def _invite_url(base_url: str, raw_token: str) -> str:
    parsed = urlsplit(base_url.strip())
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("base URL must be an absolute URL without credentials")
    is_canonical_local = parsed.hostname == "127.0.0.1"
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and is_canonical_local
    ):
        raise ValueError(
            "base URL must use HTTPS except for the canonical 127.0.0.1 host"
        )
    path = f"{parsed.path.rstrip('/')}/start"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", urlencode({"token": raw_token}))
    )


async def _create(*, base_url: str, ttl_hours: int) -> dict[str, str]:
    # Validate operator input before opening a transaction. Otherwise an invalid
    # URL would commit a live invite whose one-time raw token is never returned.
    _invite_url(base_url, "validation-only")
    async with AsyncSessionLocal() as session:
        created = await create_founder_invite(session, ttl_hours=ttl_hours)
        await session.commit()
    return {
        "status": "ok",
        "invite_id": str(created.row.id),
        "expires_at": created.row.expires_at.isoformat(),
        "invite_url": _invite_url(base_url, created.raw_token),
        "warning": "The invite URL is shown once; handle it like a credential.",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "FOUNDEROS_APP_BASE_URL", "http://127.0.0.1:3000"
        ),
        help=(
            "FounderOS web base URL "
            "(default: FOUNDEROS_APP_BASE_URL or http://127.0.0.1:3000)"
        ),
    )
    parser.add_argument(
        "--ttl-hours",
        type=int,
        default=DEFAULT_FOUNDER_INVITE_TTL_HOURS,
        help=(
            "Invite lifetime in hours "
            f"(default: {DEFAULT_FOUNDER_INVITE_TTL_HOURS}; "
            f"max: {MAX_FOUNDER_INVITE_TTL_HOURS})"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_create(base_url=args.base_url, ttl_hours=args.ttl_hours))
    except ValueError as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
