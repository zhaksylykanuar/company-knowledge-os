from __future__ import annotations

from pathlib import Path

from app.services.local_connector_env import (
    CANONICAL_CONNECTOR_ENV_KEYS,
    CANONICAL_CONNECTOR_ENV_SECTIONS,
)
from app.services.operator_output_sanitizer import inspect_operator_output

REPO_ROOT = Path(__file__).resolve().parents[1]


def _assignment_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line and not line.startswith("#") and "=" in line
    ]


def test_env_example_uses_exact_canonical_supported_key_order() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    keys = [line.split("=", 1)[0] for line in _assignment_lines(text)]

    assert keys == list(CANONICAL_CONNECTOR_ENV_KEYS)


def test_env_example_has_canonical_section_headers_and_placeholders_only() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for section_name, section_keys in CANONICAL_CONNECTOR_ENV_SECTIONS:
        assert f"# {section_name}" in text
        for key in section_keys:
            assert f"{key}=<set locally>" in text
    assert "# Legacy/local extra keys" in text
    assert inspect_operator_output(text).safe is True


def test_env_example_has_no_redundant_operator_or_connector_template_paths() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert ".env.operator" not in text
    assert ".env.local" not in text
    assert "connectors.env" not in text
