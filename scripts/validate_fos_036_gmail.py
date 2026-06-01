#!/usr/bin/env python
"""Safe FOS-036 Gmail persisted-backfill validation runner.

Default mode is local readiness only. Live mode is opt-in with ``--live`` and
performs one protected Gmail backfill request after local aggregate guards pass.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import SecretStr  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import AsyncSessionLocal, engine  # noqa: E402
from app.db.event_models import SourceEvent  # noqa: E402
from app.db.gmail_models import GmailAttachment, GmailMessage, GmailThread  # noqa: E402
from app.db.models import IngestedEvent  # noqa: E402
from app.db.source_models import DocumentChunk, SourceDocument  # noqa: E402

EXPECTED_GMAIL_COUNTS = {
    "gmail_source_events": 3,
    "gmail_documents": 3,
    "gmail_chunks": 22,
    "gmail_messages": 3,
    "gmail_threads": 3,
    "gmail_attachments": 0,
    "gmail_raw_storage_files": 4,
}

REQUIRED_CONFIG_KEYS = (
    "API_AUTH_ENABLED",
    "API_AUTH_KEY",
    "API_AUTH_HEADER_NAME",
    "GOOGLE_GMAIL_BACKFILL_ENABLED",
    "GOOGLE_GMAIL_BACKFILL_QUERY",
    "API_BASE_URL",
)

LIVE_MAX_RESULTS = 5


def _configured_secret(value: SecretStr | str | None) -> str | None:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _configured_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def config_readiness(config: Any = settings) -> dict[str, Any]:
    checks = {
        "API_AUTH_ENABLED": bool(config.api_auth_enabled),
        "API_AUTH_KEY": _configured_secret(config.api_auth_key) is not None,
        "API_AUTH_HEADER_NAME": _configured_text(config.api_auth_header_name) is not None,
        "GOOGLE_GMAIL_BACKFILL_ENABLED": bool(config.google_gmail_backfill_enabled),
        "GOOGLE_GMAIL_BACKFILL_QUERY": _configured_text(config.google_gmail_backfill_query)
        is not None,
        "API_BASE_URL": _configured_text(config.api_base_url) is not None,
    }
    present_keys = [key for key in REQUIRED_CONFIG_KEYS if checks[key]]
    missing_keys = [key for key in REQUIRED_CONFIG_KEYS if not checks[key]]
    return {
        "ready": not missing_keys,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
    }


def baseline_matches(counts: dict[str, int | None]) -> bool:
    return all(counts.get(key) == expected for key, expected in EXPECTED_GMAIL_COUNTS.items())


def safe_deltas(
    pre_counts: dict[str, int | None],
    post_counts: dict[str, int | None],
) -> dict[str, int | None]:
    deltas: dict[str, int | None] = {}
    for key in EXPECTED_GMAIL_COUNTS:
        before = pre_counts.get(key)
        after = post_counts.get(key)
        deltas[key] = after - before if isinstance(before, int) and isinstance(after, int) else None
    return deltas


async def read_gmail_counts(config: Any = settings) -> dict[str, Any]:
    counts: dict[str, int | None] = {}
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            counts["gmail_source_events"] = int(
                await session.scalar(
                    select(func.count(SourceEvent.id)).where(SourceEvent.source_system == "gmail")
                )
                or 0
            )
            counts["gmail_ingested_events"] = int(
                await session.scalar(
                    select(func.count(IngestedEvent.id)).where(
                        IngestedEvent.source_system == "gmail"
                    )
                )
                or 0
            )
            counts["gmail_documents"] = int(
                await session.scalar(
                    select(func.count(SourceDocument.id)).where(
                        SourceDocument.source_system == "gmail"
                    )
                )
                or 0
            )
            counts["gmail_chunks"] = int(
                await session.scalar(
                    select(func.count(DocumentChunk.id)).where(DocumentChunk.source_system == "gmail")
                )
                or 0
            )
            counts["gmail_messages"] = int(
                await session.scalar(select(func.count(GmailMessage.id))) or 0
            )
            counts["gmail_threads"] = int(
                await session.scalar(select(func.count(GmailThread.id))) or 0
            )
            counts["gmail_attachments"] = int(
                await session.scalar(select(func.count(GmailAttachment.id))) or 0
            )
    except Exception:
        db_status = "db_unavailable"
    finally:
        try:
            await engine.dispose()
        except Exception:
            pass

    try:
        root = Path(config.raw_storage_dir) / "gmail"
        counts["gmail_raw_storage_files"] = (
            sum(1 for path in root.rglob("*") if path.is_file()) if root.exists() else 0
        )
    except Exception:
        counts["gmail_raw_storage_files"] = None

    return {"db_status": db_status, "counts": counts}


def _safe_response_metadata(status: int | None, payload: bytes | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "request_attempted": True,
        "http_status": status,
        "avoided_http_500": status != 500 if status is not None else None,
    }
    try:
        body = json.loads((payload or b"").decode("utf-8"))
    except Exception:
        return metadata
    if not isinstance(body, dict):
        return metadata

    for source_key, output_key in (
        ("saved", "saved_count"),
        ("imported", "imported_count"),
        ("duplicates", "duplicate_count"),
        ("failed", "failed_count"),
        ("processed", "processed_count"),
        ("accepted", "accepted_count"),
        ("discovered", "discovered_count"),
    ):
        value = body.get(source_key)
        if isinstance(value, int) and output_key not in metadata:
            metadata[output_key] = value

    events = body.get("events")
    if isinstance(events, list):
        metadata["processed_count"] = len(events)
        metadata["accepted_count"] = sum(
            1 for item in events if isinstance(item, dict) and item.get("accepted") is True
        )
        metadata.setdefault(
            "failed_count",
            sum(1 for item in events if isinstance(item, dict) and item.get("accepted") is False),
        )
        metadata.setdefault(
            "duplicate_count",
            sum(1 for item in events if isinstance(item, dict) and item.get("duplicate") is True),
        )

    return metadata


def send_gmail_validation_request(config: Any = settings) -> dict[str, Any]:
    api_key = _configured_secret(config.api_auth_key)
    header_name = _configured_text(config.api_auth_header_name)
    api_base_url = _configured_text(config.api_base_url)
    if api_key is None or header_name is None or api_base_url is None:
        return {
            "request_attempted": False,
            "http_status": None,
            "avoided_http_500": None,
            "transport_error": False,
        }

    try:
        url = urljoin(api_base_url.rstrip("/") + "/", "v1/gmail/backfill")
        url = f"{url}?{urlencode({'max_results': LIVE_MAX_RESULTS, 'persist': 'true'})}"
        request = Request(url, method="POST", headers={header_name: api_key})
        with urlopen(request, timeout=90) as response:
            return _safe_response_metadata(response.getcode(), response.read())
    except HTTPError as exc:
        return _safe_response_metadata(exc.code, exc.read())
    except Exception:
        return {
            "request_attempted": True,
            "http_status": None,
            "avoided_http_500": None,
            "transport_error": True,
        }


async def run_validation(
    *,
    live: bool,
    config: Any = settings,
    count_reader: Any = read_gmail_counts,
    request_sender: Any = send_gmail_validation_request,
) -> dict[str, Any]:
    pre_result = await count_reader(config)
    pre_counts = pre_result["counts"]
    baseline_ok = pre_result["db_status"] == "ok" and baseline_matches(pre_counts)
    config_status = config_readiness(config)

    result: dict[str, Any] = {
        "mode": "live" if live else "readiness",
        "request_attempted": False,
        "db_status": pre_result["db_status"],
        "baseline_matches": baseline_ok,
        "config_ready": config_status["ready"],
        "present_config_keys": config_status["present_keys"],
        "missing_config_keys": config_status["missing_keys"],
        "pre_counts": pre_counts,
        "post_counts": None,
        "safe_deltas": None,
    }

    if not live:
        result["validation_result"] = (
            "ready_for_live"
            if baseline_ok and config_status["ready"]
            else "readiness_blocked"
        )
        return result

    if not baseline_ok:
        result["validation_result"] = "blocked_baseline_mismatch"
        return result

    if not config_status["ready"]:
        result["validation_result"] = "blocked_missing_config"
        return result

    response_metadata = request_sender(config)
    result.update(response_metadata)

    post_result = await count_reader(config)
    post_counts = post_result["counts"]
    result["post_counts"] = post_counts
    result["safe_deltas"] = safe_deltas(pre_counts, post_counts)
    result["post_db_status"] = post_result["db_status"]

    if response_metadata.get("http_status") == 202 and response_metadata.get("avoided_http_500"):
        result["validation_result"] = "passed"
    elif response_metadata.get("http_status") is None:
        result["validation_result"] = "inconclusive"
    else:
        result["validation_result"] = "failed"

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run exactly one protected Gmail persisted backfill request after guards pass.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run_validation(live=args.live))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
