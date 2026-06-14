from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.start_local import (
    HOST,
    PORT,
    build_alembic_command,
    build_uvicorn_command,
    occupied_port_message,
)

ROOT = Path(__file__).resolve().parents[1]


def test_start_local_builds_correct_uvicorn_command() -> None:
    assert HOST == "127.0.0.1"
    assert PORT == 8765
    assert build_uvicorn_command() == [
        "uv",
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]


def test_start_local_builds_alembic_upgrade_command() -> None:
    assert build_alembic_command() == ["uv", "run", "alembic", "upgrade", "head"]


def test_start_local_reports_occupied_port_clearly() -> None:
    msg = occupied_port_message()
    assert "8765" in msg
    assert "lsof -nP -iTCP:8765 -sTCP:LISTEN" in msg
    assert "http://127.0.0.1:8765/ui" in msg
    # The script must never kill the occupying process automatically.
    assert "did not stop" in msg


def test_legacy_static_founder_ui_redirects_to_ui() -> None:
    with TestClient(app) as client:
        resp = client.get("/static/founder_ui.html", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui"


def test_root_redirects_to_ui() -> None:
    with TestClient(app) as client:
        resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/ui"


def test_docs_point_to_ui_and_local_vault_not_legacy_static() -> None:
    docs = ROOT / "docs"
    for name in ("dev-env.md", "obsidian-bridge.md", "features/local-ui.md"):
        text = (docs / name).read_text(encoding="utf-8")
        assert "/ui" in text, name

    dev_env = (docs / "dev-env.md").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8765/ui" in dev_env

    bridge = (docs / "obsidian-bridge.md").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8765/ui" in bridge
    assert ".local/obsidian/FounderOS Knowledge Vault" in bridge

    local_ui = (docs / "features" / "local-ui.md").read_text(encoding="utf-8")
    assert "scripts/start_local.py" in local_ui
    assert "http://127.0.0.1:8765/ui" in local_ui
    assert "localhost:8000/ui" not in local_ui

    # No doc should send the user to the obsolete static-page route.
    for md in docs.rglob("*.md"):
        assert "/static/founder_ui.html" not in md.read_text(encoding="utf-8"), md


def test_knowledge_tree_ui_explains_obsidian_install_requirement() -> None:
    html = (ROOT / "app" / "static" / "founder_ui.html").read_text(encoding="utf-8")
    assert "Obsidian Desktop" in html
    assert "Файлы vault генерируются локально даже без Obsidian" in html
