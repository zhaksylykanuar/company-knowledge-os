#!/usr/bin/env python
"""Persist the confirmed GitHub repo -> graph mapping (A4, graph write only).

Example:
  uv run python scripts/map_github_repos.py \\
    --org qtwin-io --map qaztwin-ssap-frontend=project:qtwin \\
    --confirm-map "MAP GITHUB REPOS"
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

CONFIRM_MAP_PHRASE = "MAP GITHUB REPOS"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="GitHub organization login.")
    parser.add_argument(
        "--map",
        action="append",
        required=True,
        metavar="REPO=entity_id",
        help="Repository name to graph entity id, repeatable.",
    )
    parser.add_argument(
        "--confirm-map",
        required=True,
        help=f'Must be exactly "{CONFIRM_MAP_PHRASE}".',
    )
    return parser.parse_args(argv)


async def _run(org: str, mapping: dict[str, str]) -> int:
    from app.db.base import AsyncSessionLocal
    from app.services.github_graph_mapping import persist_github_repo_mapping

    async with AsyncSessionLocal() as session:
        counts = await persist_github_repo_mapping(session, org=org, mapping=mapping)
        await session.commit()
    print(
        "mapped: "
        f"entities_created={counts['entities_created']} "
        f"links_created={counts['links_created']} (idempotent re-run safe)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    from app.core.config import settings

    try:
        args = _parse_args(argv)
        if args.confirm_map != CONFIRM_MAP_PHRASE:
            print("Error: confirm_map phrase did not match", file=sys.stderr)
            return 2
        mapping: dict[str, str] = {}
        for item in args.map:
            if "=" not in item:
                print(f"Error: bad --map value: {item}", file=sys.stderr)
                return 2
            repo, _, entity_id = item.partition("=")
            mapping[repo.strip()] = entity_id.strip()
        prepare_script._assert_local_environment(
            settings=settings,
            environ=os.environ,
        )
        return asyncio.run(_run(args.org.strip(), mapping))
    except prepare_script.PrepareBlockedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
