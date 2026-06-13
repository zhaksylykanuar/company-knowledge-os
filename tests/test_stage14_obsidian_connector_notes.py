from __future__ import annotations

import pytest

from app.db.base import AsyncSessionLocal
from app.services.obsidian_vault import (
    _assert_markdown_safe,
    generate_obsidian_vault_plan,
)

_EXPECTED_PATHS = {
    "Sources/Jira.md",
    "Sources/GitHub.md",
    "Sources/Gmail.md",
    "Sources/Meetings.md",
    "Sources/Declarations.md",
    "_System/Connector Diagnostics.md",
}


async def test_connector_diagnostics_notes_present_and_safe() -> None:
    async with AsyncSessionLocal() as session:
        plan = await generate_obsidian_vault_plan(session)
    paths = {note.path for note in plan.notes}
    assert _EXPECTED_PATHS <= paths

    connector_notes = [
        note for note in plan.notes if note.node_type == "connector_diagnostics"
    ]
    assert len(connector_notes) >= 9
    blob = "\n".join(note.markdown for note in connector_notes)
    for forbidden in ("ghp_", "sk-", "raw://", "dev_api_key", "-----BEGIN"):
        assert forbidden not in blob
    # Each note passes the markdown safety guard.
    for note in connector_notes:
        _assert_markdown_safe(note.markdown)
        assert "## Security Policy" in note.markdown or note.path.endswith(
            "Connector Diagnostics.md"
        )


async def test_connector_notes_have_wikilinks_and_show_env_names() -> None:
    async with AsyncSessionLocal() as session:
        plan = await generate_obsidian_vault_plan(session)
    overview = next(
        note for note in plan.notes if note.path == "_System/Connector Diagnostics.md"
    )
    assert "[[Sources/Jira" in overview.markdown
    assert "[[Sources/GitHub" in overview.markdown

    github = next(note for note in plan.notes if note.path == "Sources/GitHub.md")
    # Env-var name is shown by name (setup step / missing list), never a value.
    assert "GITHUB_TOKEN" in github.markdown
    assert "Read only: `true`" in github.markdown


def test_markdown_guard_allows_names_but_blocks_values() -> None:
    # Bare environment-variable names are allowed (they are not secrets).
    _assert_markdown_safe(
        "Missing: `GITHUB_TOKEN`, `JIRA_API_TOKEN`, `GMAIL_CLIENT_SECRET`."
    )
    # Secret values and assignments are rejected.
    with pytest.raises(ValueError):
        _assert_markdown_safe("token ghp_" + "a" * 30)
    with pytest.raises(ValueError):
        _assert_markdown_safe("GITHUB_TOKEN=ghp_" + "a" * 30)
    with pytest.raises(ValueError):
        _assert_markdown_safe("see raw://gmail/body/secret")
    with pytest.raises(ValueError):
        _assert_markdown_safe("the dev_api_key must never appear")
