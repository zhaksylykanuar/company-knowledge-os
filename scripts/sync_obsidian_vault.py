#!/usr/bin/env python
"""Sync the evidence-backed knowledge graph into a local Obsidian vault.

The command writes only to the configured local vault path and only after the
explicit confirmation phrase is provided. Use ``--dry-run`` to preview changes
without filesystem writes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIRM_PHRASE = "SYNC OBSIDIAN VAULT"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-run", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def _run(*, dry_run: bool) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.obsidian_vault import build_cli_summary, sync_obsidian_vault

    async with AsyncSessionLocal() as session:
        result = await sync_obsidian_vault(session, dry_run=dry_run, requested_by="operator")
        await session.commit()
        return build_cli_summary(result)


def main() -> int:
    args = _parser().parse_args()
    if args.confirm_run != CONFIRM_PHRASE:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "missing_confirm_phrase",
                    "required": CONFIRM_PHRASE,
                    "external_side_effect": False,
                },
                ensure_ascii=False,
            )
        )
        return 2
    summary = asyncio.run(_run(dry_run=bool(args.dry_run)))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
