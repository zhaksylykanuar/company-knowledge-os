#!/usr/bin/env python3
"""Offline local-runtime readiness report for FounderOS.

This command produces a sanitized readiness packet for the local FounderOS
runtime and the separately approved provider gates. It does not start the
runtime, call a provider, or execute an external action.

The report is read-only and offline except for local ``git`` metadata commands.
It performs no provider calls, opens no network connection, touches no database,
starts no runtime, and performs no external write. It loads local environment
configuration to check whether required values are present, but never emits
those values or opens referenced credential files, provider payloads, raw smoke
responses, or internal IDs.

Usage:
    uv run python scripts/local_readiness_report.py [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.mvp_completion_audit import run_mvp_completion_audit  # noqa: E402


def _run_git(root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _git_state(root: Path) -> dict[str, Any]:
    status = _run_git(root, ["status", "--short", "--branch"])
    branch_line = status.splitlines()[0] if status else None
    dirty_paths = status.splitlines()[1:] if status else []
    ahead_count_text = _run_git(
        root,
        ["rev-list", "--count", "@{upstream}..HEAD"],
    )
    commit = _run_git(root, ["rev-parse", "--short", "HEAD"])
    return {
        "branch_line": branch_line,
        "commit": commit,
        "dirty": bool(dirty_paths),
        "dirty_path_count": len(dirty_paths),
        "ahead_count": int(ahead_count_text) if ahead_count_text and ahead_count_text.isdigit() else None,
    }


def build_local_readiness_report(
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    resolved_root = Path(root).resolve() if root is not None else ROOT

    mvp_audit = run_mvp_completion_audit(root=resolved_root).to_dict()
    git_state = _git_state(resolved_root)
    return {
        "check": "local_runtime_readiness",
        "offline": True,
        "provider_calls": False,
        "provider_writes": False,
        "local_runtime_started": False,
        "external_write_started": False,
        "env_configuration_loaded": False,
        "secret_presence_checked": False,
        "secret_values_emitted": False,
        "referenced_credential_files_read": False,
        "git": git_state,
        "mvp_audit": {
            "assessment_scope": mvp_audit["assessment_scope"],
            "local_scope_complete": mvp_audit["local_scope_complete"],
            "repository_evidence_complete": mvp_audit[
                "repository_evidence_complete"
            ],
            "runtime_acceptance_assessed": mvp_audit[
                "runtime_acceptance_assessed"
            ],
            "code_ready_for_human_gated": mvp_audit["code_ready_for_human_gated"],
            "fully_complete": mvp_audit["fully_complete"],
            "summary": mvp_audit["summary"],
            "human_gated_next_steps": mvp_audit["human_gated_next_steps"],
        },
        "provider_configuration": {
            "source_of_truth": "workspace_settings_ui",
            "checked_offline": False,
            "provider_calls_started": False,
            "next_step": "Open Settings → Integrations and use the in-product checks.",
        },
        "recommended_handoff_order": [
            "Review the exact local git snapshot before changing runtime state.",
            "Start and verify the local stack through docs/operations/local-runtime.md.",
            "Run read-only local smoke via make local-smoke.",
            "Configure and verify provider connections in Settings → Integrations.",
            "Run one explicit scoped provider read after approval.",
            "Run docs/deploy/external-action-result-smoke.md for one approved external action result.",
        ],
    }


def _print_human(report: dict[str, Any]) -> None:
    git_state = report["git"]
    mvp = report["mvp_audit"]
    print("FounderOS local runtime readiness (offline, read-only)")
    print(f"  branch: {git_state['branch_line']}")
    print(f"  commit: {git_state['commit']}")
    print(f"  ahead count: {git_state['ahead_count']}")
    print(f"  dirty working tree: {git_state['dirty']}")
    print(
        "  repository implementation evidence complete: "
        f"{mvp['repository_evidence_complete']}"
    )
    print(f"  runtime acceptance assessed: {mvp['runtime_acceptance_assessed']}")
    print(f"  full MVP complete: {mvp['fully_complete']}")
    print("  provider settings: check in Settings → Integrations")
    print("  recommended readiness order:")
    for index, step in enumerate(report["recommended_handoff_order"], start=1):
        print(f"    {index}. {step}")
    print("  note: this report starts no runtime, provider call, or external write.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    report = build_local_readiness_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
