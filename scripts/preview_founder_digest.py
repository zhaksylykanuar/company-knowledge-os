#!/usr/bin/env python
"""Preview the founder digest v2 text for a stored persisted attention window.

Read-only: builds the persisted attention read model and renders the founder
digest v2 (docs/features/telegram-digest.md). No drafts, no sends, no writes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
)
from app.services.founder_digest_rendering import (  # noqa: E402
    render_founder_attention_digest_text,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the persisted attention window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the persisted attention window.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        help=f"Maximum visible items per section, 1-{MAX_DIGEST_ENTRY_LIMIT}.",
    )
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Include synthetic local/dev seed rows (excluded by default).",
    )
    return parser.parse_args(argv)


async def _build_text(args: argparse.Namespace) -> str:
    from app.db.base import AsyncSessionLocal
    from app.services.digest import build_persisted_attention_digest_read_model

    start_at = prepare_script._parse_datetime(args.start_at, field_name="start_at")
    end_at = prepare_script._parse_datetime(args.end_at, field_name="end_at")
    limit = int(args.limit)
    if limit < 1 or limit > MAX_DIGEST_ENTRY_LIMIT:
        raise prepare_script.PrepareInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )

    marker_filter = (
        None
        if args.include_synthetic
        else PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY
    )
    async with AsyncSessionLocal() as session:
        digest = await build_persisted_attention_digest_read_model(
            session,
            start_at=start_at,
            end_at=end_at,
            limit_per_section=limit,
            marker_filter=marker_filter,
        )
    return render_founder_attention_digest_text(
        digest,
        generated_at=datetime.now(timezone.utc),
    )


def main(argv: list[str] | None = None) -> int:
    from app.core.config import settings

    try:
        args = _parse_args(argv)
        prepare_script._assert_local_environment(
            settings=settings,
            environ=os.environ,
        )
        text = asyncio.run(_build_text(args))
    except prepare_script.PrepareInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except prepare_script.PrepareBlockedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
