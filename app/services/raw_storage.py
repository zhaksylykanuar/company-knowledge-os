import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.core.config import settings


def safe_path_part(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value or "unknown").strip("-") or "unknown"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def raw_storage_root() -> Path:
    return Path(settings.raw_storage_dir)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
