#!/usr/bin/env python
"""Local repo discovery runner.

No credentials, no network. Maps the current repo's source-agent-relevant
modules and writes the result to
``.local/discovery/local-repo/<timestamp>/``.

    uv run python scripts/run_local_repo_discovery.py
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
from app.services.local_repo_discovery import (  # noqa: E402
    discover_local_repo,
    render_local_repo_audit,
)

REPORT_KIND = "local_repo_discovery_run"


def _safe_timestamp(timestamp: str) -> str:
    cleaned = "".join(c for c in str(timestamp) if c.isalnum() or c in {"-", "_"})
    return cleaned or "run"


def run(*, root: Path, timestamp: str | None = None) -> dict[str, Any]:
    summary = discover_local_repo(root)
    stamp = _safe_timestamp(timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    directory = Path(root) / DISCOVERY_LOCAL_DIRNAME / DISCOVERY_SUBDIR / "local-repo" / stamp
    directory.mkdir(parents=True, exist_ok=True)

    artifacts = [
        write_run_artifact(
            root=root, run_directory=directory, name="summary", records=summary
        ).as_dict()
    ]
    audit_md = render_local_repo_audit(summary)
    artifacts.append(
        write_run_text(
            root=root, run_directory=directory, name="local-repo-audit", text=audit_md
        ).as_dict()
    )

    result = {
        "report_kind": REPORT_KIND,
        "status": "ok",
        "run_dir": _safe_run_dir(directory, root),
        "service_module_count": summary["service_module_count"],
        "structure": summary["structure"],
        "category_counts": {k: len(v) for k, v in summary["categories"].items()},
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
