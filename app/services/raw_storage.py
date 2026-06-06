import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.production_operation_guard import (
    RAW_STORAGE_MUTATION,
    require_production_operation_ack,
)


def safe_path_part(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value or "unknown").strip("-") or "unknown"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def raw_storage_root() -> Path:
    return Path(settings.raw_storage_dir)


def write_json(
    path: Path,
    payload: Any,
    *,
    allow_production_operation: bool = False,
    production_operation_ack: str | None = None,
) -> None:
    require_production_operation_ack(
        operation_class=RAW_STORAGE_MUTATION,
        boundary="raw_storage_write_json",
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(
    path: Path,
    text: str,
    *,
    allow_production_operation: bool = False,
    production_operation_ack: str | None = None,
) -> None:
    require_production_operation_ack(
        operation_class=RAW_STORAGE_MUTATION,
        boundary="raw_storage_write_text",
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
