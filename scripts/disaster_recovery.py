"""Encrypted off-device backup export and restore-drill controls.

The local backup remains the source artifact: it already proves a PostgreSQL
restore, raw-storage integrity, and connector-credential decryptability. This
module verifies that receipt again, encrypts the exact bundle for independent
storage, and can repeat the full restore proof after downloading/decrypting it.

No command prints encryption keys, database URLs, provider data, raw file
names, or backup contents.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile
import tempfile
import time
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy.engine import make_url

from app.core.config import settings
from scripts import local_runtime


ROOT = Path(__file__).resolve().parents[1]
TARGET_MARKER = ".founderos-offsite-target.json"
TARGET_FORMAT_VERSION = 1
OFFSITE_FORMAT_VERSION = 1
OFFSITE_MAGIC = b"FOSBAK01"
NONCE_BYTES = 12
TAG_BYTES = 16
KEY_BYTES = 32
CHUNK_BYTES = 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
BACKUP_FILE_NAMES = frozenset(
    {
        "database.dump",
        "database.dump.sha256",
        "manifest.json",
        "manifest.json.sha256",
        "raw-storage.tar.gz",
        "raw-storage.tar.gz.sha256",
        "receipt.json",
    }
)


class DisasterRecoveryError(RuntimeError):
    """Sanitized recovery failure safe to show to an operator."""


@dataclass(frozen=True)
class VerifiedBundle:
    path: Path
    manifest: dict[str, Any]
    receipt: dict[str, Any]
    manifest_sha256: str


@dataclass(frozen=True)
class OffsiteBackup:
    artifact: Path
    receipt: Path
    created_at: datetime
    sha256: str


@dataclass(frozen=True)
class RetentionPolicy:
    daily: int = 7
    weekly: int = 4
    monthly: int = 12


def initialize_key_file(path: Path, *, root: Path = ROOT) -> Path:
    resolved = _new_external_path(path, root=root)
    try:
        resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise DisasterRecoveryError(
            "Recovery key directory could not be created."
        ) from exc
    _require_private_directory(resolved.parent)
    encoded = base64.urlsafe_b64encode(os.urandom(KEY_BYTES)).decode("ascii")
    try:
        descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DisasterRecoveryError("Recovery key file already exists.") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        resolved.unlink(missing_ok=True)
        raise
    return resolved


def initialize_target(
    destination: Path,
    *,
    acknowledge_independent_storage: bool,
    root: Path = ROOT,
) -> Path:
    if not acknowledge_independent_storage:
        raise DisasterRecoveryError(
            "Off-device target initialization requires the explicit independent-storage acknowledgement."
        )
    resolved = _new_external_path(destination, root=root)
    try:
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise DisasterRecoveryError(
            "Off-device backup target could not be created."
        ) from exc
    _require_private_directory(resolved)
    marker = resolved / TARGET_MARKER
    if marker.exists():
        _validate_target(resolved, root=root)
        return marker
    _write_private_json_atomic(
        marker,
        {
            "format_version": TARGET_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "independent_storage_acknowledged": True,
            "target_id": str(uuid4()),
        },
    )
    return marker


def export_verified_backup(
    *,
    target: Path,
    key_file: Path,
    receipt_path: Path | None = None,
    root: Path = ROOT,
) -> OffsiteBackup:
    resolved_target = _validate_target(target, root=root)
    key = _load_key(key_file, root=root)
    bundle = verify_local_backup_bundle(
        _select_local_receipt(receipt_path, root=root),
        root=root,
    )
    created_at = datetime.now(timezone.utc)
    artifact_name = f"founderos-offsite-{bundle.path.name}.fosbak"
    artifact = resolved_target / artifact_name
    receipt = resolved_target / f"{artifact_name}.receipt.json"
    if artifact.exists() or receipt.exists():
        raise DisasterRecoveryError("Encrypted backup artifact already exists.")

    try:
        with _private_temporary_directory(
            prefix="founderos-offsite-export-"
        ) as temporary:
            plaintext_archive = temporary / "bundle.tar"
            _create_bundle_archive(bundle, plaintext_archive)
            plaintext_sha256 = _sha256_file(plaintext_archive)
            _encrypt_file(
                plaintext_archive,
                artifact,
                key=key,
            )
            artifact_sha256 = _sha256_file(artifact)
            decrypted_archive = temporary / "verify.tar"
            _decrypt_file(artifact, decrypted_archive, key=key)
            if not hmac.compare_digest(
                plaintext_sha256,
                _sha256_file(decrypted_archive),
            ):
                raise DisasterRecoveryError("Encrypted backup verification failed.")
            extracted = temporary / "verify"
            restored_bundle_path = _extract_bundle_archive(
                decrypted_archive,
                extracted,
            )
            restored_bundle = verify_local_backup_bundle(
                restored_bundle_path / "receipt.json",
                allowed_root=temporary,
            )
            if not hmac.compare_digest(
                bundle.manifest_sha256,
                restored_bundle.manifest_sha256,
            ):
                raise DisasterRecoveryError(
                    "Encrypted backup manifest verification failed."
                )

        _write_private_json_atomic(
            receipt,
            {
                "format_version": OFFSITE_FORMAT_VERSION,
                "status": "encrypted_verified",
                "created_at": created_at.isoformat(),
                "artifact": artifact.name,
                "artifact_bytes": artifact.stat().st_size,
                "artifact_sha256": artifact_sha256,
                "encryption": "AES-256-GCM",
                "source_bundle": bundle.path.name,
                "source_manifest_sha256": bundle.manifest_sha256,
                "plaintext_archive_sha256": plaintext_sha256,
                "key_persisted_with_backup": False,
                "provider_payloads_added": False,
            },
        )
    except Exception:
        artifact.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise
    return OffsiteBackup(
        artifact=artifact,
        receipt=receipt,
        created_at=created_at,
        sha256=artifact_sha256,
    )


def drill_offsite_backup(
    *,
    target: Path,
    key_file: Path,
    artifact_path: Path | None = None,
    root: Path = ROOT,
    config: Any = settings,
) -> Path:
    started_at = time.monotonic()
    resolved_target = _validate_target(target, root=root)
    key = _load_key(key_file, root=root)
    offsite = _select_offsite_backup(
        resolved_target,
        artifact_path=artifact_path,
    )
    with _private_temporary_directory(prefix="founderos-offsite-drill-") as temporary:
        archive = temporary / "bundle.tar"
        _decrypt_file(offsite.artifact, archive, key=key)
        extracted_root = temporary / "bundle"
        bundle_path = _extract_bundle_archive(archive, extracted_root)
        bundle = verify_local_backup_bundle(
            bundle_path / "receipt.json",
            allowed_root=temporary,
        )
        proof = _restore_bundle_database(
            root=root,
            bundle=bundle,
            config=config,
        )

    drills = resolved_target / "drills"
    drills.mkdir(mode=0o700, exist_ok=True)
    _require_private_directory(drills)
    timestamp = datetime.now(timezone.utc)
    drill_receipt = drills / (
        f"restore-drill-{timestamp.strftime('%Y%m%dT%H%M%SZ')}"
        f"-{offsite.sha256[:12]}.json"
    )
    _write_private_json_atomic(
        drill_receipt,
        {
            "format_version": OFFSITE_FORMAT_VERSION,
            "status": "restore_verified",
            "verified_at": timestamp.isoformat(),
            "duration_seconds": round(time.monotonic() - started_at, 3),
            "artifact_sha256": offsite.sha256,
            "source_manifest_sha256": bundle.manifest_sha256,
            "database_restore_verified": True,
            "raw_storage_archive_verified": True,
            "temporary_database_dropped": bool(
                proof["temporary_database_dropped"]
            ),
            "credential_decryptability_verified": bool(
                proof["restored_credential_decryptability"]["verified"]
            ),
            "server_major": proof["server_major"],
            "alembic_revisions": proof["alembic_revisions"],
            "table_count": proof["table_count"],
            "total_rows": proof["total_rows"],
            "key_persisted_with_backup": False,
        },
    )
    return drill_receipt


def materialize_offsite_backup(
    *,
    target: Path,
    key_file: Path,
    output: Path,
    artifact_path: Path | None = None,
    root: Path = ROOT,
) -> Path:
    resolved_target = _validate_target(target, root=root)
    key = _load_key(key_file, root=root)
    offsite = _select_offsite_backup(
        resolved_target,
        artifact_path=artifact_path,
    )
    resolved_output = _new_external_path(output, root=root)
    if resolved_output.exists():
        raise DisasterRecoveryError("Recovery output path already exists.")
    resolved_output.mkdir(mode=0o700, parents=True)
    try:
        with _private_temporary_directory(
            prefix="founderos-offsite-materialize-"
        ) as temporary:
            archive = temporary / "bundle.tar"
            _decrypt_file(offsite.artifact, archive, key=key)
            bundle_path = _extract_bundle_archive(archive, resolved_output)
            verify_local_backup_bundle(
                bundle_path / "receipt.json",
                allowed_root=resolved_output,
            )
    except Exception:
        shutil.rmtree(resolved_output, ignore_errors=True)
        raise
    return bundle_path


def prune_offsite_backups(
    *,
    target: Path,
    policy: RetentionPolicy,
    apply: bool,
    now: datetime | None = None,
    root: Path = ROOT,
) -> tuple[int, int]:
    resolved_target = _validate_target(target, root=root)
    backups = _load_offsite_backups(resolved_target)
    keep = retained_backup_paths(
        backups,
        policy=policy,
        now=now or datetime.now(timezone.utc),
    )
    removable = [item for item in backups if item.artifact not in keep]
    if apply:
        for item in removable:
            item.artifact.unlink()
            item.receipt.unlink()
    return len(keep), len(removable)


def retained_backup_paths(
    backups: Iterable[OffsiteBackup],
    *,
    policy: RetentionPolicy,
    now: datetime,
) -> set[Path]:
    ordered = sorted(
        backups,
        key=lambda item: (item.created_at, item.artifact.name),
        reverse=True,
    )
    if not ordered:
        return set()
    if min(policy.daily, policy.weekly, policy.monthly) < 0:
        raise DisasterRecoveryError("Retention counts cannot be negative.")
    keep: set[Path] = {ordered[0].artifact}
    daily: set[str] = set()
    weekly: set[str] = set()
    monthly: set[str] = set()
    for item in ordered:
        age = now - item.created_at
        if age < timedelta(0):
            keep.add(item.artifact)
            continue
        day_key = item.created_at.strftime("%Y-%m-%d")
        week = item.created_at.isocalendar()
        week_key = f"{week.year}-W{week.week:02d}"
        month_key = item.created_at.strftime("%Y-%m")
        if age <= timedelta(days=max(policy.daily, 1)) and (
            day_key in daily or len(daily) < policy.daily
        ):
            if day_key not in daily and len(daily) < policy.daily:
                daily.add(day_key)
                keep.add(item.artifact)
            continue
        if age <= timedelta(days=max(policy.daily + policy.weekly * 7, 1)):
            if week_key not in weekly and len(weekly) < policy.weekly:
                weekly.add(week_key)
                keep.add(item.artifact)
            continue
        if month_key not in monthly and len(monthly) < policy.monthly:
            monthly.add(month_key)
            keep.add(item.artifact)
    return keep


def verify_local_backup_bundle(
    receipt_path: Path,
    *,
    root: Path | None = None,
    allowed_root: Path | None = None,
) -> VerifiedBundle:
    if receipt_path.expanduser().parent.is_symlink():
        raise DisasterRecoveryError("Local backup bundle path is invalid.")
    try:
        resolved_receipt = receipt_path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise DisasterRecoveryError("Verified local backup receipt was not found.") from exc
    if resolved_receipt.name != "receipt.json":
        raise DisasterRecoveryError("Local backup receipt path is invalid.")
    bundle = resolved_receipt.parent
    if bundle.is_symlink() or not bundle.name.startswith("founderos-"):
        raise DisasterRecoveryError("Local backup bundle path is invalid.")
    if bundle.name.endswith(".partial"):
        raise DisasterRecoveryError("Partial local backup cannot be exported.")
    boundary = (
        allowed_root.expanduser().resolve(strict=True)
        if allowed_root is not None
        else (root or ROOT).resolve() / local_runtime.BACKUP_DIR_RELATIVE
    )
    try:
        bundle.relative_to(boundary.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise DisasterRecoveryError(
            "Local backup receipt is outside the allowed backup boundary."
        ) from exc
    actual_names = {path.name for path in bundle.iterdir()}
    if actual_names != BACKUP_FILE_NAMES:
        raise DisasterRecoveryError(
            "Local backup bundle contains missing or unexpected files."
        )
    for path in bundle.iterdir():
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise DisasterRecoveryError("Local backup bundle contains an unsafe entry.")

    receipt = _read_json(resolved_receipt)
    if not _verified_local_receipt(receipt):
        raise DisasterRecoveryError("Local backup receipt is not fully verified.")
    manifest_path = bundle / "manifest.json"
    manifest_sha256 = _verify_checksum(
        manifest_path,
        bundle / "manifest.json.sha256",
    )
    if not hmac.compare_digest(
        _required_sha256(receipt, "manifest_sha256"),
        manifest_sha256,
    ):
        raise DisasterRecoveryError("Local backup manifest receipt does not match.")
    manifest = _read_json(manifest_path)
    if manifest.get("bundle_format_version") != local_runtime.BACKUP_FORMAT_VERSION:
        raise DisasterRecoveryError("Local backup format is not supported.")
    database = _required_mapping(manifest, "database")
    raw_storage = _required_mapping(manifest, "raw_storage")
    _verify_manifest_artifact(
        bundle,
        database,
        expected_name="database.dump",
    )
    raw_archive = _verify_manifest_artifact(
        bundle,
        raw_storage,
        expected_name="raw-storage.tar.gz",
    )
    expected_inventory = local_runtime.RawStorageInventory(
        source_state=_required_text(raw_storage, "source_state"),
        entries=(),
        file_count=_required_int(raw_storage, "file_count"),
        directory_count=_required_int(raw_storage, "directory_count"),
        total_bytes=_required_int(raw_storage, "total_bytes"),
        inventory_sha256=_required_sha256(
            raw_storage,
            "inventory_sha256",
        ),
    )
    try:
        local_runtime._verify_raw_storage_archive(
            raw_archive,
            expected_inventory,
        )
    except local_runtime.LocalRuntimeError as exc:
        raise DisasterRecoveryError("Raw-storage archive verification failed.") from exc
    return VerifiedBundle(
        path=bundle,
        manifest=manifest,
        receipt=receipt,
        manifest_sha256=manifest_sha256,
    )


def _restore_bundle_database(
    *,
    root: Path,
    bundle: VerifiedBundle,
    config: Any,
) -> dict[str, Any]:
    database = _required_mapping(bundle.manifest, "database")
    source_snapshot = local_runtime.DatabaseSnapshot(
        server_major=_required_int(database, "server_major"),
        alembic_revisions=tuple(
            _required_string_list(database, "alembic_revisions")
        ),
        table_counts=_required_int_mapping(database, "table_counts"),
    )
    tools = local_runtime._backup_tools()
    for binary in tools.values():
        if local_runtime._postgres_tool_major(binary) != source_snapshot.server_major:
            raise DisasterRecoveryError(
                "PostgreSQL recovery tools do not match the backup server major version."
            )
    try:
        parsed = make_url(str(config.database_url))
        return local_runtime._restore_and_compare_database(
            root=root,
            parsed=parsed,
            dump_path=bundle.path / "database.dump",
            source_snapshot=source_snapshot,
            tools=tools,
            config=config,
        )
    except local_runtime.LocalRuntimeError as exc:
        raise DisasterRecoveryError("Off-device database restore drill failed.") from exc


def _create_bundle_archive(bundle: VerifiedBundle, output: Path) -> None:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tarfile.open(output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        directory = tarfile.TarInfo(bundle.path.name)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o700
        directory.mtime = 0
        archive.addfile(directory)
        for name in sorted(BACKUP_FILE_NAMES):
            source = bundle.path / name
            info = archive.gettarinfo(
                str(source),
                arcname=f"{bundle.path.name}/{name}",
            )
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o600
            info.mtime = 0
            with source.open("rb") as stream:
                archive.addfile(info, stream)
    output.chmod(0o600)


def _extract_bundle_archive(archive_path: Path, output_root: Path) -> Path:
    output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="r:") as archive:
        members = archive.getmembers()
        directories = [member for member in members if member.isdir()]
        files = [member for member in members if member.isfile()]
        if (
            len(directories) != 1
            or len(files) != len(BACKUP_FILE_NAMES)
            or len(members) != len(directories) + len(files)
            or any(member.issym() or member.islnk() for member in members)
        ):
            raise DisasterRecoveryError("Encrypted backup archive structure is invalid.")
        bundle_name = directories[0].name
        if (
            "/" in bundle_name
            or not bundle_name.startswith("founderos-")
            or bundle_name.endswith(".partial")
        ):
            raise DisasterRecoveryError("Encrypted backup bundle name is invalid.")
        expected = {
            f"{bundle_name}/{name}" for name in BACKUP_FILE_NAMES
        }
        if {member.name for member in files} != expected:
            raise DisasterRecoveryError("Encrypted backup file inventory is invalid.")
        bundle = output_root / bundle_name
        bundle.mkdir(mode=0o700)
        for member in files:
            source = archive.extractfile(member)
            if source is None:
                raise DisasterRecoveryError("Encrypted backup file could not be read.")
            destination = bundle / Path(member.name).name
            with source, destination.open("xb") as stream:
                shutil.copyfileobj(source, stream, length=CHUNK_BYTES)
            destination.chmod(0o600)
    return bundle


def _encrypt_file(source: Path, destination: Path, *, key: bytes) -> None:
    nonce = os.urandom(NONCE_BYTES)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(OFFSITE_MAGIC)
    partial = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with source.open("rb") as input_stream, os.fdopen(
            descriptor,
            "wb",
        ) as output_stream:
            output_stream.write(OFFSITE_MAGIC)
            output_stream.write(nonce)
            while chunk := input_stream.read(CHUNK_BYTES):
                output_stream.write(encryptor.update(chunk))
            output_stream.write(encryptor.finalize())
            output_stream.write(encryptor.tag)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _decrypt_file(source: Path, destination: Path, *, key: bytes) -> None:
    try:
        size = source.stat().st_size
        if size <= len(OFFSITE_MAGIC) + NONCE_BYTES + TAG_BYTES:
            raise DisasterRecoveryError("Encrypted backup artifact is truncated.")
        with source.open("rb") as input_stream:
            magic = input_stream.read(len(OFFSITE_MAGIC))
            nonce = input_stream.read(NONCE_BYTES)
            input_stream.seek(-TAG_BYTES, os.SEEK_END)
            tag = input_stream.read(TAG_BYTES)
            ciphertext_bytes = size - len(OFFSITE_MAGIC) - NONCE_BYTES - TAG_BYTES
            input_stream.seek(len(OFFSITE_MAGIC) + NONCE_BYTES)
            if magic != OFFSITE_MAGIC or len(nonce) != NONCE_BYTES:
                raise DisasterRecoveryError("Encrypted backup header is invalid.")
            decryptor = Cipher(
                algorithms.AES(key),
                modes.GCM(nonce, tag),
            ).decryptor()
            decryptor.authenticate_additional_data(OFFSITE_MAGIC)
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as output_stream:
                    remaining = ciphertext_bytes
                    while remaining > 0:
                        chunk = input_stream.read(min(CHUNK_BYTES, remaining))
                        if not chunk:
                            raise DisasterRecoveryError(
                                "Encrypted backup artifact is truncated."
                            )
                        remaining -= len(chunk)
                        output_stream.write(decryptor.update(chunk))
                    output_stream.write(decryptor.finalize())
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
            except Exception:
                destination.unlink(missing_ok=True)
                raise
    except InvalidTag as exc:
        destination.unlink(missing_ok=True)
        raise DisasterRecoveryError(
            "Encrypted backup authentication failed."
        ) from exc
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise DisasterRecoveryError("Encrypted backup could not be read.") from exc


def _select_local_receipt(
    receipt_path: Path | None,
    *,
    root: Path,
) -> Path:
    if receipt_path is not None:
        return receipt_path
    backup_root = root.resolve() / local_runtime.BACKUP_DIR_RELATIVE
    try:
        candidates = sorted(
            (
                path
                for path in backup_root.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and path.name.startswith("founderos-")
                and not path.name.endswith(".partial")
            ),
            reverse=True,
        )
    except OSError as exc:
        raise DisasterRecoveryError("No verified local backup is available.") from exc
    if not candidates:
        raise DisasterRecoveryError("No verified local backup is available.")
    return candidates[0] / "receipt.json"


def _select_offsite_backup(
    target: Path,
    *,
    artifact_path: Path | None,
) -> OffsiteBackup:
    backups = _load_offsite_backups(target)
    if artifact_path is None:
        if not backups:
            raise DisasterRecoveryError("No encrypted off-device backup is available.")
        return max(backups, key=lambda item: (item.created_at, item.artifact.name))
    try:
        resolved = artifact_path.expanduser().resolve(strict=True)
        resolved.relative_to(target)
    except (OSError, ValueError) as exc:
        raise DisasterRecoveryError(
            "Encrypted backup artifact is outside the configured target."
        ) from exc
    for item in backups:
        if item.artifact == resolved:
            return item
    raise DisasterRecoveryError("Encrypted backup artifact has no valid receipt.")


def _load_offsite_backups(target: Path) -> list[OffsiteBackup]:
    backups: list[OffsiteBackup] = []
    for receipt_path in sorted(target.glob("*.fosbak.receipt.json")):
        receipt = _read_json(receipt_path)
        if (
            receipt.get("format_version") != OFFSITE_FORMAT_VERSION
            or receipt.get("status") != "encrypted_verified"
            or receipt.get("encryption") != "AES-256-GCM"
            or receipt.get("key_persisted_with_backup") is not False
        ):
            raise DisasterRecoveryError("Off-device backup receipt is invalid.")
        artifact_name = _required_text(receipt, "artifact")
        if Path(artifact_name).name != artifact_name or not artifact_name.endswith(
            ".fosbak"
        ):
            raise DisasterRecoveryError("Off-device backup artifact name is invalid.")
        candidate = target / artifact_name
        if candidate.is_symlink():
            raise DisasterRecoveryError("Off-device backup artifact is unsafe.")
        artifact = candidate.resolve(strict=True)
        try:
            artifact.relative_to(target)
        except ValueError as exc:
            raise DisasterRecoveryError(
                "Off-device backup artifact escaped its target."
            ) from exc
        if not artifact.is_file():
            raise DisasterRecoveryError("Off-device backup artifact is unsafe.")
        expected_sha256 = _required_sha256(receipt, "artifact_sha256")
        actual_sha256 = _sha256_file(artifact)
        if not hmac.compare_digest(expected_sha256, actual_sha256):
            raise DisasterRecoveryError("Off-device backup checksum failed.")
        created_at = _parse_timestamp(_required_text(receipt, "created_at"))
        backups.append(
            OffsiteBackup(
                artifact=artifact,
                receipt=receipt_path.resolve(strict=True),
                created_at=created_at,
                sha256=actual_sha256,
            )
        )
    return backups


def _validate_target(target: Path, *, root: Path) -> Path:
    try:
        resolved = target.expanduser().resolve(strict=True)
    except OSError as exc:
        raise DisasterRecoveryError("Off-device backup target was not found.") from exc
    _require_external_path(resolved, root=root)
    if target.is_symlink() or not resolved.is_dir():
        raise DisasterRecoveryError("Off-device backup target is unsafe.")
    _require_private_directory(resolved)
    marker = _read_json(resolved / TARGET_MARKER)
    if (
        marker.get("format_version") != TARGET_FORMAT_VERSION
        or marker.get("independent_storage_acknowledged") is not True
        or not isinstance(marker.get("target_id"), str)
    ):
        raise DisasterRecoveryError("Off-device backup target marker is invalid.")
    return resolved


def _load_key(path: Path, *, root: Path) -> bytes:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise DisasterRecoveryError("Recovery key file permissions are unsafe.")
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise DisasterRecoveryError("Recovery key file was not found.") from exc
    _require_external_path(resolved, root=root)
    metadata = resolved.lstat()
    if (
        resolved.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
    ):
        raise DisasterRecoveryError("Recovery key file permissions are unsafe.")
    try:
        encoded = resolved.read_text(encoding="ascii").strip()
        key = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (OSError, UnicodeError, binascii.Error) as exc:
        raise DisasterRecoveryError("Recovery key file is invalid.") from exc
    if len(key) != KEY_BYTES:
        raise DisasterRecoveryError("Recovery key file is invalid.")
    return key


def _new_external_path(path: Path, *, root: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    _require_external_path(resolved, root=root)
    if path.is_symlink():
        raise DisasterRecoveryError("External recovery path cannot be a symbolic link.")
    return resolved


def _require_external_path(path: Path, *, root: Path) -> None:
    repository = root.resolve()
    try:
        path.relative_to(repository)
    except ValueError:
        return
    raise DisasterRecoveryError(
        "Recovery keys, off-device targets, and materialized backups must stay outside the repository."
    )


def _require_private_directory(path: Path) -> None:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise DisasterRecoveryError("Recovery directory could not be inspected.") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise DisasterRecoveryError("Recovery path is not a directory.")
    if metadata.st_mode & 0o077:
        raise DisasterRecoveryError(
            "Recovery directory must not grant group or other access."
        )


def _verified_local_receipt(receipt: Mapping[str, Any]) -> bool:
    required_true = (
        "database_restore_verified",
        "credential_decryptability_verified",
        "backup_credential_decryptability_verified",
        "temporary_database_dropped",
        "raw_storage_archive_verified",
        "checksums_verified",
    )
    return (
        receipt.get("bundle_format_version") == local_runtime.BACKUP_FORMAT_VERSION
        and receipt.get("status") == "verified"
        and receipt.get("manifest") == "manifest.json"
        and all(receipt.get(key) is True for key in required_true)
    )


def _verify_manifest_artifact(
    bundle: Path,
    metadata: Mapping[str, Any],
    *,
    expected_name: str,
) -> Path:
    if metadata.get("artifact") != expected_name:
        raise DisasterRecoveryError("Local backup artifact name is invalid.")
    path = bundle / expected_name
    checksum = _verify_checksum(
        path,
        bundle / f"{expected_name}.sha256",
    )
    if not hmac.compare_digest(
        _required_sha256(metadata, "sha256"),
        checksum,
    ):
        raise DisasterRecoveryError("Local backup artifact manifest does not match.")
    if path.stat().st_size != _required_int(metadata, "bytes"):
        raise DisasterRecoveryError("Local backup artifact size does not match.")
    return path


def _verify_checksum(path: Path, checksum_path: Path) -> str:
    try:
        parts = checksum_path.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise DisasterRecoveryError("Backup checksum could not be read.") from exc
    if (
        len(parts) != 2
        or parts[1] != path.name
        or not _is_sha256(parts[0])
    ):
        raise DisasterRecoveryError("Backup checksum file is invalid.")
    actual = _sha256_file(path)
    if not hmac.compare_digest(parts[0], actual):
        raise DisasterRecoveryError("Backup checksum verification failed.")
    return actual


def _read_json(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_JSON_BYTES
        ):
            raise DisasterRecoveryError("Recovery metadata file is unsafe.")
        value = json.loads(path.read_text(encoding="utf-8"))
    except DisasterRecoveryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisasterRecoveryError("Recovery metadata could not be read.") from exc
    if not isinstance(value, dict):
        raise DisasterRecoveryError("Recovery metadata must be an object.")
    return value


def _write_private_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    partial = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        descriptor = os.open(
            partial,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        partial.replace(path)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise DisasterRecoveryError("Recovery metadata could not be written.") from exc


class _PrivateTemporaryDirectory:
    def __init__(self, *, prefix: str) -> None:
        self._path = Path(tempfile.mkdtemp(prefix=prefix))
        self._path.chmod(0o700)

    def __enter__(self) -> Path:
        return self._path

    def __exit__(self, *_args: object) -> None:
        shutil.rmtree(self._path, ignore_errors=True)


def _private_temporary_directory(*, prefix: str) -> _PrivateTemporaryDirectory:
    return _PrivateTemporaryDirectory(prefix=prefix)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise DisasterRecoveryError("Backup artifact could not be hashed.") from exc
    return digest.hexdigest()


def _required_mapping(
    source: Mapping[str, Any],
    key: str,
) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise DisasterRecoveryError("Recovery metadata is incomplete.")
    return dict(value)


def _required_text(source: Mapping[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DisasterRecoveryError("Recovery metadata is incomplete.")
    return value.strip()


def _required_sha256(source: Mapping[str, Any], key: str) -> str:
    value = _required_text(source, key)
    if not _is_sha256(value):
        raise DisasterRecoveryError("Recovery checksum metadata is invalid.")
    return value


def _required_int(source: Mapping[str, Any], key: str) -> int:
    value = source.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DisasterRecoveryError("Recovery numeric metadata is invalid.")
    return value


def _required_string_list(
    source: Mapping[str, Any],
    key: str,
) -> list[str]:
    value = source.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise DisasterRecoveryError("Recovery list metadata is invalid.")
    return list(value)


def _required_int_mapping(
    source: Mapping[str, Any],
    key: str,
) -> dict[str, int]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise DisasterRecoveryError("Recovery table metadata is invalid.")
    result: dict[str, int] = {}
    for raw_name, raw_count in value.items():
        if (
            not isinstance(raw_name, str)
            or not raw_name
            or not isinstance(raw_count, int)
            or isinstance(raw_count, bool)
            or raw_count < 0
        ):
            raise DisasterRecoveryError("Recovery table metadata is invalid.")
        result[raw_name] = raw_count
    return result


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DisasterRecoveryError("Recovery timestamp is invalid.") from exc
    if parsed.tzinfo is None:
        raise DisasterRecoveryError("Recovery timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _path_from_argument(value: str | None, *, env_name: str) -> Path:
    raw = value or os.environ.get(env_name)
    if not raw:
        raise DisasterRecoveryError(f"{env_name} is required.")
    return Path(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FounderOS encrypted off-device disaster recovery",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    key = subparsers.add_parser(
        "init-key",
        help="create a private 256-bit recovery key file outside the repository",
    )
    key.add_argument("--path")

    target = subparsers.add_parser(
        "init-target",
        help="mark a private directory as independently stored",
    )
    target.add_argument("--destination")
    target.add_argument(
        "--acknowledge-independent-storage",
        action="store_true",
    )

    export = subparsers.add_parser(
        "export",
        help="encrypt and verify the latest local backup",
    )
    export.add_argument("--destination")
    export.add_argument("--key-file")
    export.add_argument("--receipt")

    drill = subparsers.add_parser(
        "drill",
        help="decrypt and fully restore the latest off-device backup in isolation",
    )
    drill.add_argument("--destination")
    drill.add_argument("--key-file")
    drill.add_argument("--artifact")

    materialize = subparsers.add_parser(
        "materialize",
        help="decrypt one verified bundle for an explicitly approved recovery",
    )
    materialize.add_argument("--destination")
    materialize.add_argument("--key-file")
    materialize.add_argument("--artifact")
    materialize.add_argument("--output", required=True)

    prune = subparsers.add_parser(
        "prune",
        help="show or apply GFS retention to encrypted artifacts",
    )
    prune.add_argument("--destination")
    prune.add_argument("--daily", type=int, default=7)
    prune.add_argument("--weekly", type=int, default=4)
    prune.add_argument("--monthly", type=int, default=12)
    prune.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "init-key":
            path = _path_from_argument(
                arguments.path,
                env_name="FOUNDEROS_OFFSITE_BACKUP_KEY_FILE",
            )
            initialize_key_file(path)
            print("Recovery key file created outside the repository; preserve it separately.")
            return 0
        if arguments.command == "init-target":
            destination = _path_from_argument(
                arguments.destination,
                env_name="FOUNDEROS_OFFSITE_BACKUP_DIR",
            )
            initialize_target(
                destination,
                acknowledge_independent_storage=(
                    arguments.acknowledge_independent_storage
                ),
            )
            print("Independent off-device backup target initialized.")
            return 0
        destination = _path_from_argument(
            arguments.destination,
            env_name="FOUNDEROS_OFFSITE_BACKUP_DIR",
        )
        if arguments.command == "prune":
            kept, removable = prune_offsite_backups(
                target=destination,
                policy=RetentionPolicy(
                    daily=arguments.daily,
                    weekly=arguments.weekly,
                    monthly=arguments.monthly,
                ),
                apply=arguments.apply,
            )
            mode = "applied" if arguments.apply else "dry-run"
            print(
                f"Off-device retention {mode}: keep {kept}, remove {removable}."
            )
            return 0
        key_file = _path_from_argument(
            arguments.key_file,
            env_name="FOUNDEROS_OFFSITE_BACKUP_KEY_FILE",
        )
        artifact = Path(arguments.artifact) if arguments.artifact else None
        if arguments.command == "export":
            backup = export_verified_backup(
                target=destination,
                key_file=key_file,
                receipt_path=(
                    Path(arguments.receipt) if arguments.receipt else None
                ),
            )
            print(
                "Encrypted off-device backup verified "
                f"({backup.artifact.stat().st_size} bytes)."
            )
            return 0
        if arguments.command == "drill":
            drill_offsite_backup(
                target=destination,
                key_file=key_file,
                artifact_path=artifact,
            )
            print("Off-device recovery drill verified and temporary restore removed.")
            return 0
        if arguments.command == "materialize":
            materialize_offsite_backup(
                target=destination,
                key_file=key_file,
                output=Path(arguments.output),
                artifact_path=artifact,
            )
            print("Verified recovery bundle materialized at the approved output path.")
            return 0
    except DisasterRecoveryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, tarfile.TarError):
        print("ERROR: disaster recovery operation failed safely.", file=sys.stderr)
        return 2
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
