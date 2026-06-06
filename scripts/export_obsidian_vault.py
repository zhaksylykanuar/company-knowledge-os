from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.knowledge_score_processor import process_knowledge_scores  # noqa: E402
from app.services.obsidian_exporter import export_obsidian_vault  # noqa: E402
from app.services.production_operation_guard import (  # noqa: E402
    PRODUCTION_OPERATION_ACK,
    SOURCE_OF_TRUTH_MUTATION,
    require_production_operation_ack,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export FounderOS Postgres knowledge into a readable Obsidian vault.",
    )
    parser.add_argument(
        "--vault-path",
        default="obsidian_vault",
        help="Local Obsidian vault output path. Defaults to ./obsidian_vault.",
    )
    parser.add_argument(
        "--source-document-id",
        default=None,
        help="Optional source_document_id filter for partial export.",
    )
    parser.add_argument(
        "--refresh-scores",
        action="store_true",
        help="Refresh deterministic knowledge scores before export.",
    )
    parser.add_argument(
        "--allow-production-operation",
        action="store_true",
        help="Explicitly acknowledge this export as a production-affecting operation.",
    )
    parser.add_argument(
        "--confirm-production-operation",
        default=None,
        help=f'Must be exactly "{PRODUCTION_OPERATION_ACK}".',
    )
    return parser


async def run_export(args: argparse.Namespace) -> dict[str, Any]:
    source_document_id = args.source_document_id
    allow_production_operation = bool(
        getattr(args, "allow_production_operation", False)
    )
    production_operation_ack = getattr(args, "confirm_production_operation", None)

    require_production_operation_ack(
        operation_class=SOURCE_OF_TRUTH_MUTATION,
        boundary="obsidian_export_script",
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )

    score_result = None
    if args.refresh_scores:
        score_result = await process_knowledge_scores(
            source_document_id=source_document_id,
        )

    export_result = await export_obsidian_vault(
        vault_path=Path(args.vault_path),
        source_document_id=source_document_id,
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )

    if score_result is not None:
        export_result["score_refresh"] = score_result

    return export_result


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    result = asyncio.run(run_export(args))

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
