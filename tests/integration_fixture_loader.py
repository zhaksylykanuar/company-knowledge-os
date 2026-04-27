from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "integrations"


def load_integration_fixture(source_system: str, fixture_name: str) -> dict[str, Any]:
    fixture_path = FIXTURE_ROOT / source_system / fixture_name

    if not fixture_path.is_file():
        raise FileNotFoundError(f"Integration fixture not found: {fixture_path}")

    with fixture_path.open("r", encoding="utf-8") as file:
        fixture = json.load(file)

    if not isinstance(fixture, dict):
        raise ValueError(f"Integration fixture must be a JSON object: {fixture_path}")

    return fixture


def list_integration_fixtures(source_system: str) -> list[Path]:
    source_dir = FIXTURE_ROOT / source_system

    if not source_dir.is_dir():
        return []

    return sorted(source_dir.glob("*.json"))
