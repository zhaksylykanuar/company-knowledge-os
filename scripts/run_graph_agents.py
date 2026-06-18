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
AGENT_VERSION = "stage4.1"


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
    from datetime import datetime, timezone
    from uuid import uuid4

    from sqlalchemy import func, select

    from app.db.base import AsyncSessionLocal
    from app.db.event_models import SourceEvent
    from app.services.agent_run_log import record_agent_run
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
    from app.services.gardener_apply import apply_accepted_gardener_proposals
    from app.services.graph_gardener import run_graph_gardener
    from app.services.graph_lift import run_graph_lift
    from app.services.meeting_agent import scan_meetings
    from app.services.metric_collector import collect_metrics
    from app.services.sales_signal_agent import scan_sales_signals
    from app.services.second_opinion import scan_second_opinion

    from app.services.run_context import set_run_id

    run_id = f"run-{uuid4().hex[:16]}"
    set_run_id(run_id)  # stamps findings/proposals created or updated this run
    logged: list[tuple[str, dict, datetime, datetime]] = []

    await rebuild_email_thread_states_from_stored_gmail()

    async with AsyncSessionLocal() as session:
        watermark = str(
            (await session.execute(select(func.max(SourceEvent.id)))).scalar() or 0
        )

        async def step(agent: str, coro):
            started = datetime.now(timezone.utc)
            counts = await coro
            finished = datetime.now(timezone.utc)
            logged.append((agent, counts or {}, started, finished))
            return counts

        lift_counts = await step("graph_lift", run_graph_lift(session))
        meeting_counts = await step("meeting_agent", scan_meetings(session))
        sales_counts = await step("sales_signal_agent", scan_sales_signals(session))
        merge_suggestions = await suggest_person_merges(session)
        merge_counts = await apply_decided_merges(session)
        await step(
            "entity_identity",
            _identity_counts(merge_suggestions, merge_counts),
        )
        finding_counts = await step(
            "second_opinion", scan_second_opinion(session)
        )
        email_counts = await step(
            "email_thread_agent", scan_email_silence(session)
        )
        hypothesis_counts = await step("hypothesis_agent", scan_hypotheses(session))
        focus_counts = await step("focus_drift_agent", scan_focus_drift(session))
        gardener_counts = await step("graph_gardener", run_graph_gardener(session))
        gardener_applied = await step(
            "gardener_apply", apply_accepted_gardener_proposals(session)
        )
        metric_counts = (
            {} if args.skip_metrics else await collect_metrics(session)
        )
        if metric_counts:
            logged.append(
                (
                    "metric_collector",
                    metric_counts,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                )
            )
        availability = await refresh_data_availability(session)

        for agent, counts, started, finished in logged:
            await record_agent_run(
                session,
                run_id=run_id,
                agent=agent,
                agent_version=AGENT_VERSION,
                run_started_at=started,
                run_finished_at=finished,
                counts=counts,
                input_watermark=watermark,
            )
        await session.commit()

    print(f"run_id={run_id} agent_version={AGENT_VERSION} watermark={watermark}")
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
        "sales signals: "
        f"accounts={sales_counts['accounts']} "
        f"contacts={sales_counts['contacts']} "
        f"signals={sales_counts['signals']} "
        f"findings={sales_counts['findings']} "
        f"proposals={sales_counts['proposals']}"
    )
    # The hardening: new evidence vs a clock-based recalculation are
    # reported as separate buckets so day-rollover never looks like a find.
    print(
        "second opinion: "
        f"created={finding_counts['created']} "
        f"new_evidence={finding_counts['updated_from_new_evidence']} "
        f"clock_recalc={finding_counts['updated_from_clock_recalculation']} "
        f"unchanged={finding_counts['unchanged']} "
        f"reopened={finding_counts['reopened']} "
        f"auto_resolved={finding_counts['auto_resolved']} "
        f"errors={finding_counts['errors']}"
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
    print(
        "graph gardener: "
        f"proposals={gardener_counts['proposals']} "
        f"checked={gardener_counts['checked']} "
        f"applied={gardener_applied['applied']}"
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


async def _identity_counts(merge_suggestions: int, merge_counts: dict) -> dict:
    return {
        "merge_suggestions": merge_suggestions,
        "merges_applied": merge_counts["applied"],
        "merges_rejected": merge_counts["rejected"],
        "links_repointed": merge_counts["links_repointed"],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.confirm_run != CONFIRM_RUN_PHRASE:
        print(f'Error: pass --confirm-run "{CONFIRM_RUN_PHRASE}"')
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
