from argparse import Namespace

from app.services.production_operation_guard import PRODUCTION_OPERATION_ACK
from scripts.export_obsidian_vault import build_parser, run_export


def test_export_obsidian_vault_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.vault_path == "obsidian_vault"
    assert args.source_document_id is None
    assert args.refresh_scores is False
    assert args.allow_production_operation is False
    assert args.confirm_production_operation is None


def test_export_obsidian_vault_parser_accepts_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--vault-path",
            "custom_vault",
            "--source-document-id",
            "doc_1",
            "--refresh-scores",
            "--allow-production-operation",
            "--confirm-production-operation",
            PRODUCTION_OPERATION_ACK,
        ]
    )

    assert args.vault_path == "custom_vault"
    assert args.source_document_id == "doc_1"
    assert args.refresh_scores is True
    assert args.allow_production_operation is True
    assert args.confirm_production_operation == PRODUCTION_OPERATION_ACK


async def test_run_export_with_missing_source_document_writes_empty_vault(tmp_path) -> None:
    args = Namespace(
        vault_path=str(tmp_path),
        source_document_id="missing-source-document-for-obsidian-script-test",
        refresh_scores=False,
        allow_production_operation=True,
        confirm_production_operation=PRODUCTION_OPERATION_ACK,
    )

    result = await run_export(args)

    assert result["exported"] is True
    assert result["vault_path"] == str(tmp_path)
    assert result["source_document_id"] == (
        "missing-source-document-for-obsidian-script-test"
    )
    assert result["exported_count"] == 0
    assert result["files"] == []
