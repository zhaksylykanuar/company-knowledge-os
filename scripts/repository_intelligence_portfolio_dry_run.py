#!/usr/bin/env python3
"""Validate a private RI L0/L1 portfolio manifest without starting the run."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_MAX_MANIFEST_BYTES = 64 * 1024


class RepositoryPortfolioDryRunCLIError(RuntimeError):
    """A private manifest cannot be read through the approved boundary."""


@contextmanager
def _sanitized_process_environment() -> Iterator[None]:
    original = dict(os.environ)
    safe = {
        "FOUNDEROS_DISABLE_DOTENV": "true",
        "HOME": "/tmp",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "TMPDIR": "/tmp",
    }
    try:
        os.environ.clear()
        os.environ.update(safe)
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def read_private_portfolio_manifest(path: Path) -> bytes:
    """Read one owner-private manifest without following links or printing it."""

    if not path.is_absolute():
        raise RepositoryPortfolioDryRunCLIError("portfolio dry-run manifest path must be absolute")
    candidate = path.expanduser().absolute()
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        if resolved_parent != candidate.parent:
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest parent cannot cross a symbolic link"
            )
        if candidate.resolve(strict=False).is_relative_to(ROOT):
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest must stay outside FounderOS"
            )
    except OSError as exc:
        raise RepositoryPortfolioDryRunCLIError(
            "portfolio dry-run manifest boundary could not be verified"
        ) from exc

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor: int | None = None
    try:
        descriptor = os.open(candidate, flags)
        metadata = os.fstat(descriptor)
        path_metadata = candidate.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest must be a regular file"
            )
        if stat.S_ISLNK(path_metadata.st_mode) or (
            metadata.st_dev,
            metadata.st_ino,
        ) != (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ):
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest identity changed during validation"
            )
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest ownership is invalid"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest permissions are not private"
            )
        if metadata.st_size > _MAX_MANIFEST_BYTES:
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest exceeds the byte bound"
            )
        chunks: list[bytes] = []
        remaining = _MAX_MANIFEST_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        material = b"".join(chunks)
        if len(material) > _MAX_MANIFEST_BYTES:
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest exceeds the byte bound"
            )
        final_metadata = os.fstat(descriptor)
        if (
            final_metadata.st_dev,
            final_metadata.st_ino,
            final_metadata.st_size,
            final_metadata.st_mtime_ns,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ):
            raise RepositoryPortfolioDryRunCLIError(
                "portfolio dry-run manifest changed during validation"
            )
        return material
    except OSError as exc:
        raise RepositoryPortfolioDryRunCLIError(
            "portfolio dry-run manifest is unavailable"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(
    argv: list[str] | None = None,
    *,
    sanitize_environment: bool = True,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="absolute path to an owner-private portfolio manifest",
    )
    args = parser.parse_args(argv)
    try:
        environment = (
            _sanitized_process_environment() if sanitize_environment else _null_environment()
        )
        with environment:
            from app.services.repository_intelligence.portfolio_dry_run import (
                prepare_repository_portfolio_dry_run,
                validate_repository_portfolio_dry_run_json,
            )

            raw = read_private_portfolio_manifest(args.manifest)
            manifest = validate_repository_portfolio_dry_run_json(raw)
            receipt = prepare_repository_portfolio_dry_run(manifest)
    except Exception:
        print("ERROR: portfolio dry-run validation failed", file=sys.stderr)
        return 2
    print(receipt.deterministic_json())
    return 0


@contextmanager
def _null_environment() -> Iterator[None]:
    yield


if __name__ == "__main__":
    raise SystemExit(main())
