#!/usr/bin/env python
"""Run queued Source Control requests safely.

This operator command does not call live providers unless the operator supplies
both the run confirmation and the live-provider acknowledgement. It advances
source_run_requests through the orchestrator lifecycle and prints a sanitized
summary.
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
    parser.add_argument(
        "--allow-live-provider-execution",
        action="store_true",
        help="Allow read-only external provider calls for this orchestrator run.",
    )
    parser.add_argument(
        "--acknowledge-live-provider-risk",
        default=None,
        help="Must equal the live-provider acknowledgement phrase.",
    )
    parser.add_argument("--limit", type=int, default=25)
    return parser


async def _run(
    limit: int,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.source_run_orchestrator import run_source_requests

    async with AsyncSessionLocal() as session:
        summary = await run_source_requests(
            session,
            limit=limit,
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
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
                },
                ensure_ascii=False,
            )
        )
        return 2
    summary = asyncio.run(
        _run(
            limit=max(1, min(int(args.limit), 200)),
            allow_live_provider_execution=bool(args.allow_live_provider_execution),
            provider_execution_ack=args.acknowledge_live_provider_risk,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
