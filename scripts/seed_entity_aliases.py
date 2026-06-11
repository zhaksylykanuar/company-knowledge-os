#!/usr/bin/env python
"""Seed canonical project entities and aliases (vision Phase A2, local write).

Idempotent local/dev command: upserts the three pilot projects (SSAP, qTwin,
Integra) and their aliases into the knowledge graph tables. Writes only
entities/entity_aliases rows; no source events, triage results, drafts, or
sends.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402

CONFIRM_SEED_PHRASE = "SEED ENTITY ALIASES"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-seed",
        required=True,
        help=f'Must be exactly "{CONFIRM_SEED_PHRASE}".',
    )
    return parser.parse_args(argv)


async def _run() -> int:
    from app.db.base import AsyncSessionLocal
    from app.services.entity_resolution import seed_project_entities

    async with AsyncSessionLocal() as session:
        counts = await seed_project_entities(session)
        await session.commit()

    print(
        "seeded: "
        f"entities_created={counts['entities_created']} "
        f"aliases_created={counts['aliases_created']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    from app.core.config import settings

    try:
        args = _parse_args(argv)
        if args.confirm_seed != CONFIRM_SEED_PHRASE:
            print("Error: confirm_seed phrase did not match", file=sys.stderr)
            return 2
        prepare_script._assert_local_environment(
            settings=settings,
            environ=os.environ,
        )
        return asyncio.run(_run())
    except prepare_script.PrepareBlockedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
