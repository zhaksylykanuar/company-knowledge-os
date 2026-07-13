#!/usr/bin/env python3
"""Compatibility entrypoint for the local FounderOS readiness report.

The canonical command lives in ``scripts/local_readiness_report.py``. This
wrapper remains temporarily so existing operator commands fail neither open nor
silently while local-first documentation and Make targets are migrated.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.local_readiness_report import (  # noqa: E402
    build_local_readiness_report,
    main,
)


def build_release_handoff(**kwargs: object) -> dict[str, object]:
    """Return local readiness plus the retired handoff safety field.

    ``deploy_started`` remains only for callers of this compatibility function;
    the canonical local report has no cloud-deploy state.
    """

    report = build_local_readiness_report(**kwargs)
    report["deploy_started"] = False
    return report


if __name__ == "__main__":
    raise SystemExit(main())
