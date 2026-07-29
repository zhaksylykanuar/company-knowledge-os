from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tarfile

import pytest

from scripts import disaster_recovery, local_runtime


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _write_checksum(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    checksum.chmod(0o600)
    return digest


def _verified_bundle(root: Path) -> Path:
    bundle = root / ".local/backups/founderos-20260729T120000000000Z-deadbeef"
    bundle.mkdir(mode=0o700, parents=True)
    database = bundle / "database.dump"
    database.write_bytes(b"private-db-record")
    database.chmod(0o600)
    database_sha = _write_checksum(database)

    raw_archive = bundle / "raw-storage.tar.gz"
    raw_content = b"private-raw-record"
    with tarfile.open(raw_archive, mode="w:gz") as archive:
        info = tarfile.TarInfo("raw_storage/item.txt")
        info.size = len(raw_content)
        import io

        archive.addfile(info, io.BytesIO(raw_content))
    raw_archive.chmod(0o600)
    raw_sha = _write_checksum(raw_archive)
    entries = (
        local_runtime.RawStorageEntry(
            Path(),
            "item.txt",
            "file",
            len(raw_content),
            hashlib.sha256(raw_content).hexdigest(),
        ),
    )

    manifest = {
        "bundle_format_version": local_runtime.BACKUP_FORMAT_VERSION,
        "created_at": "2026-07-29T12:00:00+00:00",
        "database": {
            "artifact": database.name,
            "bytes": database.stat().st_size,
            "sha256": database_sha,
            "server_major": 16,
            "alembic_revisions": ["head"],
            "table_counts": {"workspaces": 1},
            "table_count": 1,
            "total_rows": 1,
            "temporary_database_dropped": True,
            "restored_credential_decryptability": {
                "verified": True,
                "verified_field_count": 0,
                "fixture_field_count": 0,
            },
        },
        "credential_decryptability": {
            "verified": True,
            "verified_field_count": 0,
            "fixture_field_count": 0,
        },
        "raw_storage": {
            "artifact": raw_archive.name,
            "bytes": raw_archive.stat().st_size,
            "sha256": raw_sha,
            "source_state": "present",
            "file_count": 1,
            "directory_count": 0,
            "total_bytes": len(raw_content),
            "inventory_sha256": local_runtime._raw_inventory_digest(entries),
            "symlinks_allowed": False,
        },
    }
    manifest_path = bundle / "manifest.json"
    _write_json(manifest_path, manifest)
    manifest_sha = _write_checksum(manifest_path)
    _write_json(
        bundle / "receipt.json",
        {
            "bundle_format_version": local_runtime.BACKUP_FORMAT_VERSION,
            "status": "verified",
            "verified_at": "2026-07-29T12:01:00+00:00",
            "manifest": manifest_path.name,
            "manifest_sha256": manifest_sha,
            "database_restore_verified": True,
            "credential_decryptability_verified": True,
            "backup_credential_decryptability_verified": True,
            "temporary_database_dropped": True,
            "raw_storage_archive_verified": True,
            "checksums_verified": True,
        },
    )
    return bundle / "receipt.json"


def _recovery_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    root.mkdir(mode=0o700)
    key_directory = tmp_path / "key"
    key_directory.mkdir(mode=0o700)
    key_file = key_directory / "recovery.key"
    target = tmp_path / "offsite"
    disaster_recovery.initialize_key_file(key_file, root=root)
    disaster_recovery.initialize_target(
        target,
        acknowledge_independent_storage=True,
        root=root,
    )
    return root, key_file, target


def test_export_encrypts_exact_verified_bundle_and_materializes_it(
    tmp_path: Path,
) -> None:
    root, key_file, target = _recovery_paths(tmp_path)
    receipt = _verified_bundle(root)

    exported = disaster_recovery.export_verified_backup(
        target=target,
        key_file=key_file,
        receipt_path=receipt,
        root=root,
    )

    assert exported.artifact.is_file()
    assert exported.receipt.is_file()
    assert b"private-db-record" not in exported.artifact.read_bytes()
    assert b"private-raw-record" not in exported.artifact.read_bytes()
    offsite_receipt = json.loads(exported.receipt.read_text(encoding="utf-8"))
    assert offsite_receipt["status"] == "encrypted_verified"
    assert offsite_receipt["encryption"] == "AES-256-GCM"
    assert offsite_receipt["key_persisted_with_backup"] is False

    output = tmp_path / "recovered"
    bundle = disaster_recovery.materialize_offsite_backup(
        target=target,
        key_file=key_file,
        output=output,
        root=root,
    )
    assert (bundle / "database.dump").read_bytes() == b"private-db-record"
    assert {path.name for path in bundle.iterdir()} == (
        disaster_recovery.BACKUP_FILE_NAMES
    )


def test_offsite_restore_drill_writes_sanitized_proof(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, key_file, target = _recovery_paths(tmp_path)
    receipt = _verified_bundle(root)
    exported = disaster_recovery.export_verified_backup(
        target=target,
        key_file=key_file,
        receipt_path=receipt,
        root=root,
    )

    monkeypatch.setattr(
        disaster_recovery,
        "_restore_bundle_database",
        lambda **_kwargs: {
            "temporary_database_dropped": True,
            "restored_credential_decryptability": {"verified": True},
            "server_major": 16,
            "alembic_revisions": ["head"],
            "table_count": 1,
            "total_rows": 1,
        },
    )
    drill_receipt = disaster_recovery.drill_offsite_backup(
        target=target,
        key_file=key_file,
        artifact_path=exported.artifact,
        root=root,
        config=object(),
    )

    proof = json.loads(drill_receipt.read_text(encoding="utf-8"))
    assert proof["status"] == "restore_verified"
    assert proof["database_restore_verified"] is True
    assert proof["raw_storage_archive_verified"] is True
    assert proof["temporary_database_dropped"] is True
    serialized = json.dumps(proof)
    assert "private-db-record" not in serialized
    assert "private-raw-record" not in serialized


def test_tampering_and_unsafe_paths_fail_closed(tmp_path: Path) -> None:
    root, key_file, target = _recovery_paths(tmp_path)
    receipt = _verified_bundle(root)
    exported = disaster_recovery.export_verified_backup(
        target=target,
        key_file=key_file,
        receipt_path=receipt,
        root=root,
    )
    with exported.artifact.open("r+b") as stream:
        stream.seek(len(disaster_recovery.OFFSITE_MAGIC) + 2)
        current = stream.read(1)
        stream.seek(-1, 1)
        stream.write(bytes([current[0] ^ 1]))

    with pytest.raises(
        disaster_recovery.DisasterRecoveryError,
        match="checksum",
    ):
        disaster_recovery.materialize_offsite_backup(
            target=target,
            key_file=key_file,
            output=tmp_path / "recovered",
            root=root,
        )

    with pytest.raises(
        disaster_recovery.DisasterRecoveryError,
        match="outside the repository",
    ):
        disaster_recovery.initialize_target(
            root / "offsite",
            acknowledge_independent_storage=True,
            root=root,
        )

    key_link = tmp_path / "linked-recovery.key"
    key_link.symlink_to(key_file)
    with pytest.raises(
        disaster_recovery.DisasterRecoveryError,
        match="permissions are unsafe",
    ):
        disaster_recovery.export_verified_backup(
            target=target,
            key_file=key_link,
            receipt_path=receipt,
            root=root,
        )


def test_retention_is_dry_run_by_default_and_keeps_newest(
    tmp_path: Path,
) -> None:
    root, _key_file, target = _recovery_paths(tmp_path)
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    artifacts: list[Path] = []
    for offset in (0, 1, 2, 8, 15, 45, 75, 450):
        created_at = now - timedelta(days=offset)
        artifact = target / f"founderos-offsite-{offset:03d}.fosbak"
        artifact.write_bytes(f"ciphertext-{offset}".encode())
        artifact.chmod(0o600)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        _write_json(
            target / f"{artifact.name}.receipt.json",
            {
                "format_version": disaster_recovery.OFFSITE_FORMAT_VERSION,
                "status": "encrypted_verified",
                "created_at": created_at.isoformat(),
                "artifact": artifact.name,
                "artifact_sha256": digest,
                "encryption": "AES-256-GCM",
                "key_persisted_with_backup": False,
            },
        )
        artifacts.append(artifact)

    policy = disaster_recovery.RetentionPolicy(daily=2, weekly=2, monthly=2)
    kept, removable = disaster_recovery.prune_offsite_backups(
        target=target,
        policy=policy,
        apply=False,
        now=now,
        root=root,
    )
    assert kept >= 1
    assert removable >= 1
    assert all(path.exists() for path in artifacts)

    disaster_recovery.prune_offsite_backups(
        target=target,
        policy=policy,
        apply=True,
        now=now,
        root=root,
    )
    assert artifacts[0].exists()
    assert sum(path.exists() for path in artifacts) == kept
