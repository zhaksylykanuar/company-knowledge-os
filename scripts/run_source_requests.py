#!/usr/bin/env python
"""Run queued Source Control requests safely.

This operator command does not call live providers with the default adapter
registry. It advances source_run_requests through the orchestrator lifecycle
and prints a sanitized summary.
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

CONFIRM_PHRASE = "RUN SOURCE REQUESTS"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-run", required=True)
    parser.add_argument("--limit", type=int, default=25)
    return parser


async def _run(limit: int) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.source_run_orchestrator import run_source_requests

    async with AsyncSessionLocal() as session:
        summary = await run_source_requests(session, limit=limit)
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
                },
                ensure_ascii=False,
            )
        )
        return 2
    summary = asyncio.run(_run(limit=max(1, min(int(args.limit), 200))))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
