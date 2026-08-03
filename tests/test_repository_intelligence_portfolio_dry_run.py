from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.repository_intelligence.portfolio_dry_run import (
    RepositoryPortfolioDryRunEntryV1,
    RepositoryPortfolioDryRunError,
    RepositoryPortfolioDryRunManifestV1,
    RepositoryPortfolioSourceMode,
    prepare_repository_portfolio_dry_run,
    validate_repository_portfolio_dry_run_json,
)


WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")
REPOSITORY_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_REPOSITORY_ID = UUID("33333333-3333-4333-8333-333333333333")


def _entry(
    *,
    repository_id: UUID = REPOSITORY_ID,
    external_id: str = "repository-1",
    full_name: str = "synthetic-company/repository-one",
    source_mode: RepositoryPortfolioSourceMode = (RepositoryPortfolioSourceMode.PROVIDER_EXACT_SHA),
    local_mirror_ref: str | None = None,
) -> RepositoryPortfolioDryRunEntryV1:
    return RepositoryPortfolioDryRunEntryV1(
        repository_id=repository_id,
        external_id=external_id,
        full_name=full_name,
        commit_sha="a" * 40,
        audit_levels=["L0", "L1"],
        profile="repository-static-v1",
        policy_hash="b" * 64,
        engine_version="ri-engine-1.0.0",
        source_mode=source_mode,
        local_mirror_ref=local_mirror_ref,
    )


def _manifest(
    *repositories: RepositoryPortfolioDryRunEntryV1,
) -> RepositoryPortfolioDryRunManifestV1:
    return RepositoryPortfolioDryRunManifestV1(
        schema_version="repository_portfolio_dry_run.v1",
        workspace_id=WORKSPACE_ID,
        l2_enabled=False,
        provider_calls_authorized=False,
        target_reads_authorized=False,
        target_execution_authorized=False,
        persistence_authorized=False,
        repositories=list(repositories) or [_entry()],
    )


def test_dry_run_returns_content_free_l0_l1_receipt() -> None:
    manifest = _manifest(
        _entry(),
        _entry(
            repository_id=OTHER_REPOSITORY_ID,
            external_id="repository-2",
            full_name="synthetic-company/repository-two",
            source_mode=RepositoryPortfolioSourceMode.OPERATOR_MANAGED_LOCAL_MIRROR,
            local_mirror_ref="approved-mirrors/repository-two",
        ),
    )

    receipt = prepare_repository_portfolio_dry_run(manifest)
    material = receipt.deterministic_json()

    assert receipt.status == "ready_for_separate_run_approval"
    assert receipt.repository_count == 2
    assert receipt.l0_repository_count == 2
    assert receipt.l1_repository_count == 2
    assert receipt.exact_sha_count == 2
    assert receipt.provider_source_count == 1
    assert receipt.local_mirror_source_count == 1
    assert receipt.l2_enabled is False
    assert receipt.provider_calls_performed == 0
    assert receipt.target_paths_opened == 0
    assert receipt.target_repositories_read == 0
    assert receipt.target_code_executed == 0
    assert receipt.analysis_jobs_enqueued == 0
    assert receipt.persistence_writes == 0
    assert receipt.external_writes == 0
    assert receipt.artifact_retention_days == 30
    assert receipt.checkout_retention == "deleted_on_exit"
    assert "synthetic-company" not in material
    assert "approved-mirrors" not in material
    assert "a" * 40 not in material


def test_dry_run_does_not_touch_provider_paths_database_or_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry run crossed an execution boundary")

    monkeypatch.setattr(Path, "exists", blocked)
    monkeypatch.setattr(Path, "open", blocked)
    monkeypatch.setattr(Path, "read_text", blocked)
    monkeypatch.setattr(Path, "read_bytes", blocked)

    receipt = prepare_repository_portfolio_dry_run(_manifest(_entry()))

    assert receipt.repository_count == 1
    assert receipt.rollback == "no_runtime_mutation_in_dry_run"


@pytest.mark.parametrize(
    "audit_levels",
    (["L0"], ["L1"], ["L0", "L1", "L2"], ["L1", "L0", "L0"]),
)
def test_dry_run_requires_exact_l0_l1_and_forbids_l2(
    audit_levels: list[str],
) -> None:
    payload = _entry().model_dump(mode="json")
    payload["audit_levels"] = audit_levels

    with pytest.raises(ValidationError):
        RepositoryPortfolioDryRunEntryV1.model_validate(payload)


@pytest.mark.parametrize(
    "commit_sha",
    ("a" * 7, "A" * 40, "g" * 40),
)
def test_dry_run_requires_exact_full_sha(commit_sha: str) -> None:
    payload = _entry().model_dump(mode="json")
    payload["commit_sha"] = commit_sha

    with pytest.raises(ValidationError):
        RepositoryPortfolioDryRunEntryV1.model_validate(payload)


def test_dry_run_rejects_absolute_traversal_and_missing_mirror_refs() -> None:
    for value in ("/private/repository", "../repository", "mirror/../repository"):
        with pytest.raises(ValidationError):
            _entry(
                source_mode=(RepositoryPortfolioSourceMode.OPERATOR_MANAGED_LOCAL_MIRROR),
                local_mirror_ref=value,
            )

    with pytest.raises(ValidationError):
        _entry(source_mode=RepositoryPortfolioSourceMode.OPERATOR_MANAGED_LOCAL_MIRROR)

    with pytest.raises(ValidationError):
        _entry(local_mirror_ref="approved-mirrors/repository-one")


def test_dry_run_rejects_duplicate_identities_and_unknown_fields() -> None:
    first = _entry()
    duplicate = _entry(repository_id=OTHER_REPOSITORY_ID)
    with pytest.raises(ValidationError):
        _manifest(first, duplicate)

    payload = _manifest(first).model_dump(mode="json")
    payload["provider_token"] = "must-not-be-accepted"
    with pytest.raises(ValidationError):
        RepositoryPortfolioDryRunManifestV1.model_validate(payload)

    with pytest.raises(ValidationError):
        _manifest(
            _entry(
                repository_id=OTHER_REPOSITORY_ID,
                external_id="repository-2",
                full_name="synthetic-company/z-repository",
            ),
            _entry(full_name="synthetic-company/a-repository"),
        )


def test_dry_run_rejects_authorization_to_read_execute_persist_or_enable_l2() -> None:
    for field in (
        "l2_enabled",
        "provider_calls_authorized",
        "target_reads_authorized",
        "target_execution_authorized",
        "persistence_authorized",
    ):
        payload = _manifest(_entry()).model_dump(mode="json")
        payload[field] = True
        with pytest.raises(ValidationError):
            RepositoryPortfolioDryRunManifestV1.model_validate(payload)


def test_dry_run_receipt_rejects_inconsistent_counts() -> None:
    receipt = prepare_repository_portfolio_dry_run(_manifest(_entry()))
    payload = receipt.model_dump(mode="json")
    payload["l1_repository_count"] = 2

    with pytest.raises(ValidationError):
        type(receipt).model_validate(payload)


def test_raw_json_validation_is_bounded_and_sanitized() -> None:
    payload = _manifest(_entry()).model_dump(mode="json")
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    assert validate_repository_portfolio_dry_run_json(raw) == _manifest(_entry())

    with pytest.raises(RepositoryPortfolioDryRunError) as malformed:
        validate_repository_portfolio_dry_run_json("{not-json")
    assert "not-json" not in str(malformed.value)

    with pytest.raises(RepositoryPortfolioDryRunError):
        validate_repository_portfolio_dry_run_json(b"x" * (64 * 1024 + 1))


def test_private_manifest_cli_emits_only_content_free_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.repository_intelligence_portfolio_dry_run import main

    manifest_path = tmp_path / "portfolio.json"
    manifest_path.write_text(
        json.dumps(_manifest(_entry()).model_dump(mode="json")),
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)

    assert (
        main(
            ["--manifest", str(manifest_path)],
            sanitize_environment=False,
        )
        == 0
    )
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert receipt["status"] == "ready_for_separate_run_approval"
    assert receipt["repository_count"] == 1
    assert "synthetic-company" not in captured.out
    assert "repository-1" not in captured.out
    assert str(manifest_path) not in captured.out
    assert captured.err == ""


def test_private_manifest_cli_rejects_nonprivate_symlink_and_repo_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.repository_intelligence_portfolio_dry_run import main

    manifest_path = tmp_path / "portfolio.json"
    manifest_path.write_text(
        json.dumps(_manifest(_entry()).model_dump(mode="json")),
        encoding="utf-8",
    )
    manifest_path.chmod(0o644)
    assert (
        main(
            ["--manifest", str(manifest_path)],
            sanitize_environment=False,
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: portfolio dry-run validation failed\n"

    symlinked_parent = tmp_path / "linked-parent"
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    symlinked_parent.symlink_to(real_parent, target_is_directory=True)
    nested = real_parent / "portfolio.json"
    nested.write_text(
        json.dumps(_manifest(_entry()).model_dump(mode="json")),
        encoding="utf-8",
    )
    nested.chmod(0o600)
    assert (
        main(
            ["--manifest", str(symlinked_parent / "portfolio.json")],
            sanitize_environment=False,
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: portfolio dry-run validation failed\n"

    manifest_path.chmod(0o600)
    link = tmp_path / "portfolio-link.json"
    link.symlink_to(manifest_path)
    assert (
        main(
            ["--manifest", str(link)],
            sanitize_environment=False,
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: portfolio dry-run validation failed\n"


def test_documented_cli_invocation_runs_from_repository_root(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "portfolio.json"
    manifest_path.write_text(
        json.dumps(_manifest(_entry()).model_dump(mode="json")),
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/repository_intelligence_portfolio_dry_run.py",
            "--manifest",
            str(manifest_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "ready_for_separate_run_approval"
    assert receipt["provider_calls_performed"] == 0
    assert receipt["target_repositories_read"] == 0
    assert "synthetic-company" not in completed.stdout
    assert str(manifest_path) not in completed.stdout
    assert completed.stderr == ""


def test_cli_sanitizes_ambient_environment_before_contract_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.repository_intelligence_portfolio_dry_run import main

    manifest_path = tmp_path / "portfolio.json"
    manifest_path.write_text(
        json.dumps(_manifest(_entry()).model_dump(mode="json")),
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)
    marker = "ambient-secret-marker"
    monkeypatch.setenv("FOUNDEROS_SECRET_ENCRYPTION_KEY", marker)
    monkeypatch.setenv("DATABASE_URL", f"postgresql://{marker}@example.invalid/db")

    assert main(["--manifest", str(manifest_path)]) == 0
    captured = capsys.readouterr()
    assert marker not in captured.out
    assert marker not in captured.err
    assert os.environ["FOUNDEROS_SECRET_ENCRYPTION_KEY"] == marker
