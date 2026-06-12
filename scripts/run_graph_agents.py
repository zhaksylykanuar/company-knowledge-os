#!/usr/bin/env python
"""Run local graph agents: lift people/knowledge into the graph + metrics.

Deterministic, provider-free, idempotent. Writes only graph entities,
entity links, agent proposals, and metric snapshots. Never calls
external APIs and never mutates source-of-truth ingestion rows.

Example:
  uv run python scripts/run_graph_agents.py --confirm-run "RUN GRAPH AGENTS"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIRM_RUN_PHRASE = "RUN GRAPH AGENTS"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-run",
        required=True,
        help=f'Must be exactly "{CONFIRM_RUN_PHRASE}".',
    )
    parser.add_argument(
        "--skip-metrics",
        action="store_true",
        help="Run only the graph lift, skip the daily metric snapshot.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    from app.db.base import AsyncSessionLocal
    from app.services.graph_lift import run_graph_lift
    from app.services.metric_collector import collect_metrics

    async with AsyncSessionLocal() as session:
        lift_counts = await run_graph_lift(session)
        metric_counts = (
            {} if args.skip_metrics else await collect_metrics(session)
        )
        await session.commit()

    print(
        "graph lift: "
        f"people_created={lift_counts['people_created']} "
        f"nodes_created={lift_counts['nodes_created']} "
        f"links_created={lift_counts['links_created']} "
        f"merge_proposals={lift_counts['merge_proposals']}"
    )
    if metric_counts:
        print(
            "metrics: "
            f"created={metric_counts['created']} "
            f"updated={metric_counts['updated']} "
            f"unchanged={metric_counts['unchanged']}"
        )
    print("(idempotent re-run safe; uncertain facts went to agent_proposals)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.confirm_run != CONFIRM_RUN_PHRASE:
        print(f'Error: pass --confirm-run "{CONFIRM_RUN_PHRASE}"')
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
