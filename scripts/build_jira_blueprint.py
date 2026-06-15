#!/usr/bin/env python
"""Build the target Jira blueprint deliverable from local discovery outputs.

Offline. Combines the static target model (`docs/ops/jira-target-blueprint.md`)
with the latest discovery-derived inputs and writes
``.local/discovery/package/<timestamp>/target-jira-blueprint.md``. No provider
calls, no writes.

    uv run python scripts/build_jira_blueprint.py
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
    write_run_text,
)
from app.services.discovery_package import (  # noqa: E402
    build_target_jira_blueprint,
    load_latest_summary,
)

REPORT_KIND = "jira_blueprint_build"
BLUEPRINT_DOC = "docs/ops/jira-target-blueprint.md"


def _safe_timestamp(timestamp: str) -> str:
    cleaned = "".join(c for c in str(timestamp) if c.isalnum() or c in {"-", "_"})
    return cleaned or "run"


def run(*, root: Path, timestamp: str | None = None) -> dict[str, Any]:
    root = Path(root)
    jira_summary = load_latest_summary(root, "jira")
    github_summary = load_latest_summary(root, "github")
    base = (
        (root / BLUEPRINT_DOC).read_text(encoding="utf-8")
        if (root / BLUEPRINT_DOC).is_file()
        else ""
    )

    content = build_target_jira_blueprint(jira_summary, github_summary, base_text=base)

    stamp = _safe_timestamp(timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    directory = root / DISCOVERY_LOCAL_DIRNAME / DISCOVERY_SUBDIR / "package" / stamp
    directory.mkdir(parents=True, exist_ok=True)
    ref = write_run_text(
        root=root, run_directory=directory, name="target-jira-blueprint", text=content
    )

    result = {
        "report_kind": REPORT_KIND,
        "status": "ok",
        "inputs": {
            "jira_discovery_present": bool(jira_summary),
            "github_discovery_present": bool(github_summary),
        },
        "artifact": ref.as_dict(),
    }
    return assert_summary_safe(result)


def main(argv: list[str] | None = None) -> int:
    result = run(root=REPO_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
