#!/usr/bin/env python
"""Assemble the 8-file discovery package from local discovery outputs.

Offline. Reads the latest local Jira/GitHub/local-repo discovery summaries and
writes the founder-facing package to ``.local/discovery/package/<timestamp>/``.
No provider calls, no writes to Jira/GitHub.

    uv run python scripts/export_discovery_package.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.discovery_core import (  # noqa: E402
    DISCOVERY_LOCAL_DIRNAME,
    DISCOVERY_SUBDIR,
    assert_summary_safe,
    write_run_artifact,
    write_run_text,
)
from app.services.discovery_package import (  # noqa: E402
    PACKAGE_FILES,
    build_discovery_package,
    find_latest_run,
    load_latest_summary,
)

REPORT_KIND = "discovery_package_export"
BLUEPRINT_DOC = "docs/ops/jira-target-blueprint.md"


def _read_latest_text(root: Path, source: str, filename: str) -> str:
    run = find_latest_run(root, source)
    if run is None:
        return ""
    path = run / filename
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _safe_timestamp(timestamp: str) -> str:
    cleaned = "".join(c for c in str(timestamp) if c.isalnum() or c in {"-", "_"})
    return cleaned or "run"


def run(*, root: Path, timestamp: str | None = None) -> dict[str, Any]:
    root = Path(root)
    jira_summary = load_latest_summary(root, "jira")
    github_summary = load_latest_summary(root, "github")
    local_summary = load_latest_summary(root, "local-repo")
    blueprint_base = (
        (root / BLUEPRINT_DOC).read_text(encoding="utf-8")
        if (root / BLUEPRINT_DOC).is_file()
        else ""
    )

    package = build_discovery_package(
        jira_summary=jira_summary,
        github_summary=github_summary,
        local_summary=local_summary,
        jira_audit_md=_read_latest_text(root, "jira", "current-jira-audit.md"),
        github_audit_md=_read_latest_text(root, "github", "github-repo-audit.md"),
        blueprint_base_text=blueprint_base,
    )

    stamp = _safe_timestamp(timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    directory = root / DISCOVERY_LOCAL_DIRNAME / DISCOVERY_SUBDIR / "package" / stamp
    directory.mkdir(parents=True, exist_ok=True)

    artifacts = []
    for filename in PACKAGE_FILES:
        stem, _, ext = filename.rpartition(".")
        content = package[filename]
        if ext == "json":
            ref = write_run_artifact(root=root, run_directory=directory, name=stem, records=content)
        else:
            ref = write_run_text(
                root=root, run_directory=directory, name=stem, text=content, extension=ext
            )
        artifacts.append(ref.as_dict())

    result = {
        "report_kind": REPORT_KIND,
        "status": "ok",
        "run_dir": _safe_run_dir(directory, root),
        "deliverables_created": len(artifacts),
        "deliverables": [a["artifact_name"] for a in artifacts],
        "inputs": {
            "jira_discovery_present": bool(jira_summary),
            "github_discovery_present": bool(github_summary),
            "local_repo_discovery_present": bool(local_summary),
        },
        "planned_write_action_count": package["dry-run-write-plan.json"]["planned_action_count"],
        "artifacts": artifacts,
    }
    return assert_summary_safe(result)


def _safe_run_dir(directory: Path, root: Path) -> str:
    try:
        return str(directory.relative_to(Path(root)))
    except ValueError:
        return str(directory)


def main(argv: list[str] | None = None) -> int:
    result = run(root=REPO_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
