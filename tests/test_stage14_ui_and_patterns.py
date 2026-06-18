from __future__ import annotations

from pathlib import Path

from app.services.secret_patterns import assert_no_secret_values, contains_secret_value

ROOT = Path(__file__).resolve().parents[1]


def test_sources_ui_renders_connector_diagnostics_wizard() -> None:
    html = (ROOT / "app" / "static" / "founder_ui.html").read_text(encoding="utf-8")
    for marker in (
        "connectorDiagBlock",
        "/v1/founder/connectors/diagnostics",
        "CONNECTOR_DIAGS",
        "missing env vars (names only)",
        "Setup wizard",
        "no secrets to browser",
        "adapter: ",
    ):
        assert marker in html, marker


def test_secret_patterns_allow_names_block_values() -> None:
    # Names are not secrets.
    assert contains_secret_value("GITHUB_TOKEN") is False
    assert contains_secret_value("Missing: JIRA_API_TOKEN, GMAIL_CLIENT_SECRET") is False
    assert contains_secret_value("GITHUB_TOKEN: missing") is False
    # Real values are flagged.
    assert contains_secret_value("ghp_" + "a" * 30) is True
    assert contains_secret_value("sk-" + "b" * 30) is True
    assert contains_secret_value("GITHUB_TOKEN=ghp_" + "c" * 30) is True
    assert contains_secret_value("raw://gmail/body/x") is True


def test_assert_no_secret_values_walks_nested_structures() -> None:
    safe = {
        "connectors": [
            {"missing_env_vars": ["GITHUB_TOKEN", "JIRA_API_TOKEN"], "configured": False}
        ]
    }
    assert_no_secret_values(safe)

    unsafe = {"connectors": [{"value": "ghp_" + "d" * 30}]}
    try:
        assert_no_secret_values(unsafe)
    except ValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError for secret value")
