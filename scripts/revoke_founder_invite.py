#!/usr/bin/env python
"""Revoke an unconsumed founder invite by its durable invite ID.

The raw invite token is neither accepted nor required.  Use the ``invite_id``
printed by ``create_founder_invite.py``.

Usage:
  UV_NO_SYNC=1 uv run python scripts/revoke_founder_invite.py \
      --invite-id 00000000-0000-0000-0000-000000000000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.services.founder_enrollment_service import (  # noqa: E402
    FounderInviteRevocationError,
    revoke_founder_invite,
)


async def _revoke(invite_id: UUID) -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        try:
            invite = await revoke_founder_invite(session, invite_id=invite_id)
            await session.commit()
        except FounderInviteRevocationError:
            await session.rollback()
            raise
    assert invite.revoked_at is not None
    return {
        "status": "ok",
        "invite_id": str(invite.id),
        "revoked_at": invite.revoked_at.isoformat(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--invite-id",
        type=UUID,
        required=True,
        help="Durable invite UUID returned by create_founder_invite.py",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_revoke(args.invite_id))
    except FounderInviteRevocationError as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
