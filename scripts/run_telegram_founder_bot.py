#!/usr/bin/env python
"""Run the founder Telegram bot loop (vision Phase A1, operator-launched).

Long-polls getUpdates and answers allowlisted founder messages with the
founder digest v2 built from stored data. Read-only: no DB writes, no
drafts/intentions/results. Live Telegram calls require the human-typed
provider execution acknowledgement phrase.
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

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
)
from app.services.provider_execution_guard import (  # noqa: E402
    LIVE_PROVIDER_EXECUTION_ACK,
)
from app.services.telegram_founder_bot import (  # noqa: E402
    DEFAULT_POLL_TIMEOUT_SECONDS,
    DEFAULT_STATUS_WINDOW_HOURS,
    run_founder_bot_iteration,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acknowledge-live-provider-risk",
        required=True,
        help=f'Must be exactly "{LIVE_PROVIDER_EXECUTION_ACK}".',
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=DEFAULT_STATUS_WINDOW_HOURS,
        help="Trailing window for /status replies.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        help=f"Maximum visible items per section, 1-{MAX_DIGEST_ENTRY_LIMIT}.",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=DEFAULT_POLL_TIMEOUT_SECONDS,
        help="getUpdates long-poll timeout in seconds.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Stop after N polls (0 = run until interrupted).",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    from app.core.config import settings

    bot_token = settings.telegram_bot_token or ""
    chat_id = settings.telegram_chat_id or ""
    if not bot_token.strip() or not chat_id.strip():
        print(
            "Error: telegram bot token / chat id are not configured in .env",
            file=sys.stderr,
        )
        return 1

    offset: int | None = None
    iterations = 0
    print("founder bot: polling started (Ctrl+C to stop)")
    while True:
        result = await run_founder_bot_iteration(
            bot_token=bot_token,
            allowed_chat_id=chat_id,
            offset=offset,
            window_hours=args.window_hours,
            limit=args.limit,
            poll_timeout_seconds=args.poll_timeout,
            allow_live_provider_execution=True,
            provider_execution_ack=args.acknowledge_live_provider_risk,
        )
        if result.blocked_reason is not None:
            print(f"Error: blocked by provider guard: {result.blocked_reason}", file=sys.stderr)
            return 1
        if result.updates_seen:
            print(
                "founder bot: "
                f"updates={result.updates_seen} "
                f"allowed={result.updates_from_allowed_chat} "
                f"replied={result.replies_sent}"
            )
        offset = result.next_offset
        iterations += 1
        if args.max_iterations and iterations >= args.max_iterations:
            print("founder bot: max iterations reached, stopping")
            return 0


def main(argv: list[str] | None = None) -> int:
    from app.core.config import settings

    try:
        args = _parse_args(argv)
        prepare_script._assert_local_environment(
            settings=settings,
            environ=os.environ,
        )
        return asyncio.run(_run(args))
    except prepare_script.PrepareBlockedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nfounder bot: stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
