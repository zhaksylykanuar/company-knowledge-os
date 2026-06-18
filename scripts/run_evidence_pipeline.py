#!/usr/bin/env python
"""Run the normalized-evidence to graph/finding pipeline safely.

The command is local/operator-only. It reads persisted normalized activity,
updates local graph/proposal/finding read models, writes audit/run-log rows,
and never calls external providers.
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

CONFIRM_PHRASE = "RUN EVIDENCE PIPELINE"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-run", required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--sync-obsidian",
        action="store_true",
        help="After the pipeline, explicitly sync the local Obsidian vault if configured.",
    )
    return parser


async def _run(limit: int, *, sync_obsidian: bool = False) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.evidence_graph_lift import run_evidence_pipeline
    from app.services.obsidian_vault import build_cli_summary, sync_obsidian_vault

    async with AsyncSessionLocal() as session:
        summary = await run_evidence_pipeline(session, limit=limit)
        if sync_obsidian:
            summary["obsidian_sync"] = build_cli_summary(
                await sync_obsidian_vault(
                    session,
                    dry_run=False,
                    requested_by="operator",
                )
            )
        await session.commit()
        return summary


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
    summary = asyncio.run(
        _run(
            limit=max(1, min(int(args.limit), 1000)),
            sync_obsidian=bool(args.sync_obsidian),
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
