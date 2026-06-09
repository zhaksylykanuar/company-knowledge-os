from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.drive as drive_api
import app.api.gmail as gmail_api
from app.main import app
from app.services.production_operation_guard import (
    DELIVERY_EXECUTION,
    OBSIDIAN_VAULT_MUTATION,
    PRODUCTION_OPERATION_ACK,
    PRODUCTION_OPERATION_ACK_REQUIRED,
    PRODUCTION_OPERATION_ALLOWED,
    PRODUCTION_OPERATION_DEFAULT_DENIED,
    RAW_STORAGE_MUTATION,
    SOURCE_OF_TRUTH_MUTATION,
    ProductionOperationBlockedError,
    require_production_operation_ack,
)
from app.services.telegram_delivery import TelegramDeliveryResult

REPO_ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_OPERATION_BOUNDARY_INVENTORY = {
    "scripts/send_test_telegram_delivery_intention.py::_send_bounded_chunks": (
        "guarded_delivery_execution"
    ),
    "scripts/send_test_telegram_delivery_intention.py::execute_test_send": (
        "bounded_operator_gate"
    ),
    "app/services/obsidian_exporter.py::export_obsidian_vault": (
        "guarded_obsidian_vault_mutation"
    ),
    "scripts/export_obsidian_vault.py::run_export": (
        "guarded_source_of_truth_export"
    ),
    "app/services/raw_storage.py::write_json": "guarded_raw_storage_mutation",
    "app/services/raw_storage.py::write_text": "guarded_raw_storage_mutation",
    "app/services/knowledge_ingestion.py::ingest_text": "guarded_source_of_truth_mutation",
    "app/api/knowledge.py::ingest_text_endpoint": "guarded_source_of_truth_mutation",
    "app/api/knowledge.py::ingest_text_process_endpoint": (
        "guarded_source_of_truth_mutation"
    ),
    "app/api/gmail.py::gmail_backfill": "guarded_source_of_truth_mutation",
    "app/api/drive.py::drive_backfill": "guarded_source_of_truth_mutation",
}

GUARDED_OPERATION_FILES = {
    "app/api/drive.py",
    "app/api/gmail.py",
    "app/api/knowledge.py",
    "app/services/knowledge_ingestion.py",
    "app/services/obsidian_exporter.py",
    "app/services/raw_storage.py",
    "scripts/export_obsidian_vault.py",
    "scripts/send_test_telegram_delivery_intention.py",
}


def test_production_operation_guard_default_denies_without_ack() -> None:
    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        require_production_operation_ack(
            operation_class=DELIVERY_EXECUTION,
            boundary="test_telegram_delivery_execution",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics == {
        "operation_class": DELIVERY_EXECUTION,
        "boundary": "test_telegram_delivery_execution",
        "reason_code": PRODUCTION_OPERATION_DEFAULT_DENIED,
        "allowed": False,
    }


def test_production_operation_guard_requires_exact_operator_ack() -> None:
    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        require_production_operation_ack(
            operation_class=OBSIDIAN_VAULT_MUTATION,
            boundary="obsidian_export_vault",
            allow_production_operation=True,
            production_operation_ack="wrong_ack",
        )

    diagnostics = exc_info.value.diagnostics.as_dict()
    assert diagnostics["reason_code"] == PRODUCTION_OPERATION_ACK_REQUIRED
    assert diagnostics["allowed"] is False
    assert PRODUCTION_OPERATION_ACK not in repr(diagnostics)


def test_production_operation_guard_allows_explicit_ack() -> None:
    diagnostics = require_production_operation_ack(
        operation_class=OBSIDIAN_VAULT_MUTATION,
        boundary="obsidian_export_vault",
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    assert diagnostics.as_dict() == {
        "operation_class": OBSIDIAN_VAULT_MUTATION,
        "boundary": "obsidian_export_vault",
        "reason_code": PRODUCTION_OPERATION_ALLOWED,
        "allowed": True,
    }


def test_production_operation_boundary_inventory_uses_safe_categories_only() -> None:
    assert set(PRODUCTION_OPERATION_BOUNDARY_INVENTORY.values()) <= {
        "guarded_delivery_execution",
        "bounded_operator_gate",
        "guarded_obsidian_vault_mutation",
        "guarded_raw_storage_mutation",
        "guarded_source_of_truth_export",
        "guarded_source_of_truth_mutation",
        "source_of_truth_mutation_future_scope",
    }
    assert all("://" not in boundary for boundary in PRODUCTION_OPERATION_BOUNDARY_INVENTORY)


def test_known_operation_boundary_files_use_shared_guard() -> None:
    for relative_path in GUARDED_OPERATION_FILES:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert (
            "require_production_operation_ack" in source
            or "ProductionOperationBlockedError" in source
        )


def test_raw_storage_default_denies_before_filesystem_write(tmp_path: Path) -> None:
    from app.services import raw_storage

    output_path = tmp_path / "raw" / "payload.json"

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        raw_storage.write_json(output_path, {"safe": "synthetic"})

    assert exc_info.value.reason_code == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert exc_info.value.diagnostics.operation_class == RAW_STORAGE_MUTATION
    assert not output_path.exists()
    assert not output_path.parent.exists()


def test_raw_storage_allows_explicit_ack_with_synthetic_path(tmp_path: Path) -> None:
    from app.services import raw_storage

    output_path = tmp_path / "raw" / "content.txt"

    raw_storage.write_text(
        output_path,
        "synthetic content",
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "synthetic content"


async def test_manual_ingestion_default_denies_before_raw_or_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import knowledge_ingestion

    raw_path_called = False
    session_called = False

    def forbidden_build_raw_path(*args: Any, **kwargs: Any) -> Path:
        nonlocal raw_path_called
        raw_path_called = True
        raise AssertionError("default-denied ingestion must not touch raw storage")

    def forbidden_session_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal session_called
        session_called = True
        raise AssertionError("default-denied ingestion must not open a DB session")

    monkeypatch.setattr(knowledge_ingestion, "_build_raw_path", forbidden_build_raw_path)
    monkeypatch.setattr(knowledge_ingestion, "AsyncSessionLocal", forbidden_session_factory)

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        await knowledge_ingestion.ingest_text(
            title="Synthetic note",
            text="Synthetic note body",
        )

    assert exc_info.value.reason_code == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert exc_info.value.diagnostics.operation_class == SOURCE_OF_TRUTH_MUTATION
    assert raw_path_called is False
    assert session_called is False


async def test_bounded_delivery_default_denies_before_send_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import send_test_telegram_delivery_intention as send_script

    send_called = False

    async def forbidden_send_telegram_plain_text(
        **kwargs: Any,
    ) -> TelegramDeliveryResult:
        nonlocal send_called
        send_called = True
        raise AssertionError("default-denied delivery execution must not send")

    monkeypatch.setattr(
        "app.services.telegram_delivery.send_telegram_plain_text",
        forbidden_send_telegram_plain_text,
    )

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        await send_script._send_bounded_chunks(
            bot_token="<set locally>",
            chat_id="TELEGRAM_CHAT_ID",
            chunks=["synthetic digest"],
            transport=None,
        )

    assert exc_info.value.reason_code == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert send_called is False


async def test_bounded_delivery_allows_explicit_ack_with_synthetic_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import send_test_telegram_delivery_intention as send_script

    calls: list[dict[str, Any]] = []

    async def fake_send_telegram_plain_text(**kwargs: Any) -> TelegramDeliveryResult:
        calls.append(dict(kwargs))
        return TelegramDeliveryResult(
            success=True,
            attempted_chunks=1,
            sent_chunks=1,
            message_ids=("synthetic-message",),
        )

    monkeypatch.setattr(
        "app.services.telegram_delivery.send_telegram_plain_text",
        fake_send_telegram_plain_text,
    )

    result = await send_script._send_bounded_chunks(
        bot_token="<set locally>",
        chat_id="TELEGRAM_CHAT_ID",
        chunks=["synthetic digest"],
        transport=None,
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    assert result.attempted_chunk_count == 1
    assert result.delivered_chunk_count == 1
    assert len(calls) == 1


async def test_obsidian_export_default_denies_before_collect_or_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.services import obsidian_exporter

    collect_called = False
    write_called = False

    async def forbidden_collect_obsidian_entities(**kwargs: Any) -> list[Any]:
        nonlocal collect_called
        collect_called = True
        raise AssertionError("default-denied Obsidian export must not collect")

    def forbidden_write_obsidian_entities(**kwargs: Any) -> list[Path]:
        nonlocal write_called
        write_called = True
        raise AssertionError("default-denied Obsidian export must not write")

    monkeypatch.setattr(
        obsidian_exporter,
        "collect_obsidian_entities",
        forbidden_collect_obsidian_entities,
    )
    monkeypatch.setattr(
        obsidian_exporter,
        "write_obsidian_entities",
        forbidden_write_obsidian_entities,
    )

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        await obsidian_exporter.export_obsidian_vault(vault_path=tmp_path)

    assert exc_info.value.reason_code == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert collect_called is False
    assert write_called is False


async def test_obsidian_export_allows_explicit_ack_with_synthetic_writers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.services import obsidian_exporter

    async def fake_collect_obsidian_entities(**kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(
        obsidian_exporter,
        "collect_obsidian_entities",
        fake_collect_obsidian_entities,
    )
    monkeypatch.setattr(obsidian_exporter, "write_obsidian_entities", lambda **kwargs: [])
    monkeypatch.setattr(obsidian_exporter, "write_obsidian_index_files", lambda **kwargs: [])

    result = await obsidian_exporter.export_obsidian_vault(
        vault_path=tmp_path,
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    assert result["exported"] is True
    assert result["exported_count"] == 0
    assert result["files"] == []


async def test_export_script_default_denies_before_score_refresh_or_export(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts import export_obsidian_vault as export_script

    score_called = False
    export_called = False

    async def forbidden_process_knowledge_scores(**kwargs: Any) -> dict[str, Any]:
        nonlocal score_called
        score_called = True
        raise AssertionError("default-denied export script must not refresh scores")

    async def forbidden_export_obsidian_vault(**kwargs: Any) -> dict[str, Any]:
        nonlocal export_called
        export_called = True
        raise AssertionError("default-denied export script must not export")

    monkeypatch.setattr(
        export_script,
        "process_knowledge_scores",
        forbidden_process_knowledge_scores,
    )
    monkeypatch.setattr(
        export_script,
        "export_obsidian_vault",
        forbidden_export_obsidian_vault,
    )

    args = Namespace(
        vault_path=str(tmp_path),
        source_document_id="synthetic_source_document",
        refresh_scores=True,
        allow_production_operation=False,
        confirm_production_operation=None,
    )

    with pytest.raises(ProductionOperationBlockedError) as exc_info:
        await export_script.run_export(args)

    assert exc_info.value.reason_code == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert score_called is False
    assert export_called is False


def test_gmail_backfill_persist_default_denies_before_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gmail_api.settings, "api_auth_enabled", False)
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_enabled", True)
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_query", "label:synthetic")

    connector_called = False

    def forbidden_list_messages(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal connector_called
        connector_called = True
        raise AssertionError("default-denied Gmail persist must not call connector")

    monkeypatch.setattr(gmail_api, "list_messages", forbidden_list_messages)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"persist": "true"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert connector_called is False


def test_drive_backfill_persist_default_denies_before_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(drive_api.settings, "api_auth_enabled", False)
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", True)
    monkeypatch.setattr(drive_api.settings, "google_drive_ai_inbox_folder_id", "synthetic")

    connector_called = False

    def forbidden_list_files(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal connector_called
        connector_called = True
        raise AssertionError("default-denied Drive persist must not call connector")

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", forbidden_list_files)

    with TestClient(app) as client:
        response = client.post(
            "/v1/drive/backfill",
            params={"persist": "true"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == PRODUCTION_OPERATION_DEFAULT_DENIED
    assert connector_called is False
