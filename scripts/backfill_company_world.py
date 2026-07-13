#!/usr/bin/env python
"""Dry-run or explicitly apply the local durable Company World backfill."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.services.company_world_backfill_service import (  # noqa: E402
    backfill_company_world,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Plan the Company World profile backfill. Writes occur only with --apply.")
    )
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the idempotent local backfill after reviewing dry-run counts.",
    )
    return parser


async def _run(*, workspace_id: UUID, apply: bool) -> dict:
    async with AsyncSessionLocal() as session:
        report = await backfill_company_world(
            session,
            workspace_id,
            apply=apply,
        )
        if apply:
            await session.commit()
        else:
            await session.rollback()
        return report


def main() -> int:
    args = _parser().parse_args()
    report = asyncio.run(_run(workspace_id=args.workspace_id, apply=args.apply))
    print(json.dumps(report, default=str, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
