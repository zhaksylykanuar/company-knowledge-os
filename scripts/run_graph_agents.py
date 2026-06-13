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
    from app.services.data_availability import refresh_data_availability
    from app.services.declaration_agents import scan_focus_drift, scan_hypotheses
    from app.services.email_thread_agent import scan_email_silence
    from app.services.email_threads import (
        rebuild_email_thread_states_from_stored_gmail,
    )
    from app.services.entity_identity import (
        apply_decided_merges,
        suggest_person_merges,
    )
    from app.services.graph_lift import run_graph_lift
    from app.services.meeting_agent import scan_meetings
    from app.services.metric_collector import collect_metrics
    from app.services.second_opinion import scan_second_opinion

    await rebuild_email_thread_states_from_stored_gmail()

    async with AsyncSessionLocal() as session:
        lift_counts = await run_graph_lift(session)
        meeting_counts = await scan_meetings(session)
        merge_suggestions = await suggest_person_merges(session)
        merge_counts = await apply_decided_merges(session)
        finding_counts = await scan_second_opinion(session)
        email_counts = await scan_email_silence(session)
        hypothesis_counts = await scan_hypotheses(session)
        focus_counts = await scan_focus_drift(session)
        metric_counts = (
            {} if args.skip_metrics else await collect_metrics(session)
        )
        availability = await refresh_data_availability(session)
        await session.commit()

    print(
        "graph lift: "
        f"people_created={lift_counts['people_created']} "
        f"nodes_created={lift_counts['nodes_created']} "
        f"links_created={lift_counts['links_created']}"
    )
    print(
        "identity: "
        f"merge_suggestions={merge_suggestions} "
        f"merges_applied={merge_counts['applied']} "
        f"merges_rejected={merge_counts['rejected']} "
        f"links_repointed={merge_counts['links_repointed']}"
    )
    print(
        "meetings: "
        f"meetings={meeting_counts['meetings']} "
        f"decisions={meeting_counts['decisions']} "
        f"actions={meeting_counts['action_items']} "
        f"risks={meeting_counts['risks']}"
    )
    print(
        "second opinion: "
        f"created={finding_counts['created']} "
        f"updated={finding_counts['updated']} "
        f"unchanged={finding_counts['unchanged']} "
        f"reopened={finding_counts['reopened']} "
        f"auto_resolved={finding_counts['auto_resolved']}"
    )
    print(
        "email silence: "
        f"created={email_counts['created']} "
        f"proposed={email_counts['proposed']} "
        f"unchanged={email_counts['unchanged']}"
    )
    print(
        "declarations: "
        f"hypotheses={hypothesis_counts['hypotheses']} "
        f"hyp_findings={hypothesis_counts['findings']} "
        f"focus_findings={focus_counts['findings']}"
    )
    if metric_counts:
        print(
            "metrics: "
            f"created={metric_counts['created']} "
            f"updated={metric_counts['updated']} "
            f"unchanged={metric_counts['unchanged']}"
        )
    print(f"data availability rows: {availability['rows']}")
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
