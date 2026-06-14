#!/usr/bin/env python
"""Run a safe local connector pilot end-to-end.

One command to drive the connector E2E chain locally:

  diagnostics -> test -> sync -> evidence pipeline -> Obsidian dry-run

Safety:
- Requires the confirmation phrase.
- Real external reads happen ONLY when the operator set both the credentials
  and ``FOUNDEROS_ENABLE_REAL_CONNECTORS=true``. When real connectors are
  disabled or a source is missing config, NO external network call is made — the
  pilot just records what to do next.
- Read-only: no writes to Jira/GitHub/Gmail, no email sent.
- Obsidian is previewed (dry-run) by default; a real vault write happens only
  with ``--sync-obsidian``.
- No secrets are printed; only env-var names and sanitized statuses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIRM_PHRASE = "RUN LOCAL CONNECTOR PILOT"
REAL_PILOT_SOURCES = ("jira", "github")


def _empty_summary(real_enabled: bool, connectors_checked: int) -> dict[str, Any]:
    return {
        "status": "completed",
        "real_execution_enabled": real_enabled,
        "external_side_effect": False,
        "connectors_checked": connectors_checked,
        "test_requests_created": 0,
        "sync_requests_created": 0,
        "source_runs_succeeded": 0,
        "source_runs_failed": 0,
        "source_runs_skipped_missing_config": 0,
        "source_runs_skipped_real_disabled": 0,
        "events_ingested": 0,
        "normalized_events": 0,
        "graph_nodes_updated": 0,
        "findings_created": 0,
        "obsidian_notes_would_update": 0,
        "obsidian_notes_updated": 0,
        "warnings": [],
        "next_steps": [],
    }


def _ingestion(row: Any) -> dict[str, Any]:
    result = row.result_summary if isinstance(row.result_summary, dict) else {}
    sanitized = result.get("sanitized_summary") if isinstance(result, dict) else {}
    if not isinstance(sanitized, dict):
        return {}
    ingestion = sanitized.get("ingestion")
    return ingestion if isinstance(ingestion, dict) else {}


def _run_mode(row: Any) -> str | None:
    result = row.result_summary if isinstance(row.result_summary, dict) else {}
    sanitized = result.get("sanitized_summary") if isinstance(result, dict) else {}
    return sanitized.get("mode") if isinstance(sanitized, dict) else None


def _bucket_run(summary: dict[str, Any], run: dict[str, Any], row: Any) -> None:
    status = run.get("status")
    connector_status = run.get("connector_status")
    if status == "succeeded":
        summary["source_runs_succeeded"] += 1
    elif status == "failed":
        summary["source_runs_failed"] += 1
    elif status in {"skipped", "skipped_paused", "unchanged"}:
        if connector_status == "missing_config":
            summary["source_runs_skipped_missing_config"] += 1
        elif _run_mode(row) == "real_connectors_disabled":
            summary["source_runs_skipped_real_disabled"] += 1
    ingestion = _ingestion(row)
    summary["events_ingested"] += int(ingestion.get("events_ingested") or 0)
    summary["normalized_events"] += int(ingestion.get("normalized_events") or 0)


async def _run_request(
    session: Any,
    *,
    source_type: str,
    action_type: str,
    request_key: str,
    connectors: dict[str, Any] | None,
) -> tuple[dict[str, Any], Any]:
    from sqlalchemy import select

    from app.db.source_control_models import SourceRunRequest
    from app.services.source_control import request_source_action
    from app.services.source_run_orchestrator import run_source_request

    requested = await request_source_action(
        session,
        source_type=source_type,
        action_type=action_type,
        request_key=request_key,
        requested_by="pilot",
    )
    row = await session.scalar(
        select(SourceRunRequest).where(
            SourceRunRequest.request_id == requested["request_id"]
        )
    )
    run = await run_source_request(session, request=row, connectors=connectors)
    refreshed = await session.scalar(
        select(SourceRunRequest).where(
            SourceRunRequest.request_id == requested["request_id"]
        )
    )
    return run, refreshed


async def run_pilot(
    session: Any,
    *,
    run_key: str,
    connectors: dict[str, Any] | None = None,
    sync_obsidian: bool = False,
    evidence_limit: int = 200,
) -> dict[str, Any]:
    """Pilot core (testable without bootstrap/alembic).

    With injected ``connectors`` (fakes), no real network is used.
    """

    from app.services.connector_diagnostics import build_connector_diagnostics
    from app.services.evidence_graph_lift import run_evidence_pipeline
    from app.services.obsidian_vault import sync_obsidian_vault
    from app.services.secret_patterns import assert_no_secret_values

    diagnostics = await build_connector_diagnostics(session)
    real_enabled = bool(diagnostics.get("real_execution_enabled"))
    summary = _empty_summary(real_enabled, len(diagnostics.get("connectors") or []))
    warnings: list[str] = []
    by_type = {c["source_type"]: c for c in diagnostics.get("connectors") or []}

    # Phase 1: test requests for configured + real-enabled external connectors.
    for source_type in REAL_PILOT_SOURCES:
        connector = by_type.get(source_type)
        if connector is None:
            continue
        if not connector.get("configured"):
            warnings.append(f"{source_type}: missing_config — no external call made")
            continue
        if not real_enabled:
            warnings.append(
                f"{source_type}: configured but real connectors disabled — "
                "no external call made"
            )
            continue
        run, row = await _run_request(
            session,
            source_type=source_type,
            action_type="test",
            request_key=f"pilot-test-{source_type}-{run_key}",
            connectors=connectors,
        )
        summary["test_requests_created"] += 1
        _bucket_run(summary, run, row)

    # Phase 2: sync requests for connectors whose test just succeeded.
    if summary["test_requests_created"]:
        after_test = await build_connector_diagnostics(session)
        after_by_type = {c["source_type"]: c for c in after_test.get("connectors") or []}
        for source_type in REAL_PILOT_SOURCES:
            connector = after_by_type.get(source_type)
            if connector is None or not real_enabled:
                continue
            if connector.get("pipeline_state") in {
                "test_succeeded",
                "sync_succeeded",
                "connected",
            }:
                run, row = await _run_request(
                    session,
                    source_type=source_type,
                    action_type="sync",
                    request_key=f"pilot-sync-{source_type}-{run_key}",
                    connectors=connectors,
                )
                summary["sync_requests_created"] += 1
                _bucket_run(summary, run, row)

    # Phase 3: local evidence pipeline (no external calls).
    evidence = await run_evidence_pipeline(session, limit=evidence_limit)
    summary["graph_nodes_updated"] += int(
        (evidence.get("graph_nodes_created") or 0)
        + (evidence.get("graph_nodes_updated") or 0)
    )
    summary["findings_created"] += int(evidence.get("findings_created") or 0)

    # Phase 4: Obsidian preview (dry-run); real write only with the flag.
    dry = await sync_obsidian_vault(session, dry_run=True, requested_by="pilot")
    summary["obsidian_notes_would_update"] = int(
        (dry.get("notes_created") or 0) + (dry.get("notes_updated") or 0)
    )
    if sync_obsidian:
        real = await sync_obsidian_vault(session, dry_run=False, requested_by="pilot")
        summary["obsidian_notes_updated"] = int(
            (real.get("notes_created") or 0) + (real.get("notes_updated") or 0)
        )

    final = await build_connector_diagnostics(session)
    summary["warnings"] = warnings
    summary["next_steps"] = list((final.get("pilot") or {}).get("next_steps") or [])
    assert_no_secret_values(summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-run", required=True)
    parser.add_argument(
        "--sync-obsidian",
        action="store_true",
        help="Write the local Obsidian vault (otherwise dry-run only).",
    )
    parser.add_argument("--evidence-limit", type=int, default=200)
    return parser


async def _run_main(*, sync_obsidian: bool, evidence_limit: int) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal

    run_key = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    async with AsyncSessionLocal() as session:
        summary = await run_pilot(
            session,
            run_key=run_key,
            sync_obsidian=sync_obsidian,
            evidence_limit=evidence_limit,
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

    from scripts.bootstrap_local_workspace import bootstrap_local_workspace

    bootstrap_local_workspace(repo_root=ROOT, apply=True)
    alembic = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=ROOT)
    if alembic.returncode != 0:
        return alembic.returncode
    summary = asyncio.run(
        _run_main(
            sync_obsidian=bool(args.sync_obsidian),
            evidence_limit=max(1, min(int(args.evidence_limit), 1000)),
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
