#!/usr/bin/env python3
"""Offline MVP completion audit CLI for FounderOS.

This command maps every playbook MVP requirement (§1.5) and every main
end-to-end flow step (§1.4) to authoritative in-repository evidence and prints
what is locally complete versus what remains human/external gated.

It is read-only and offline: it performs no GitHub/provider calls, opens no
network connection, touches no database, and never prints secrets, tokens, env
values, or credential contents. It only reports requirement names, statuses, and
missing-evidence file markers.

Usage:
    uv run python scripts/mvp_completion_audit.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.mvp_completion_audit import (  # noqa: E402
    run_mvp_completion_audit,
)

_STATUS_LABEL = {
    "complete_local": "OK (local)",
    "code_ready_human_gated": "CODE-READY (human-gated)",
    "missing": "MISSING",
}


def _print_human(report: dict[str, object]) -> None:
    summary = report["summary"]
    print("FounderOS MVP completion audit (offline, read-only)")
    print(f"  local scope complete: {report['local_scope_complete']}")
    print(f"  fully complete (incl. human-gated): {report['fully_complete']}")
    print(
        "  items present: "
        f"{summary['present']}/{summary['total']} "
        f"(local {summary['local_present']}/{summary['local_total']}, "
        f"human-gated {summary['human_gated_present']}/{summary['human_gated_total']})"
    )
    print()
    for item in report["items"]:
        label = _STATUS_LABEL.get(str(item["status"]), str(item["status"]))
        print(f"  [{label}] {item['category']}: {item['requirement']}")
        for missing in item["missing_evidence"]:
            print(f"      missing: {missing}")
    human_steps = report["human_gated_next_steps"]
    if human_steps:
        print()
        print("  Human/external next steps (cannot be auto-completed in-repo):")
        for step in human_steps:
            print(f"    - {step['requirement']}: {step['human_note']}")
    print()
    print("  note: this audit starts no provider call, deploy, or external write.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    audit = run_mvp_completion_audit()
    report = audit.to_dict()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
