"""Local repo discovery: filename-based map, no network, no contents read."""

from __future__ import annotations

from pathlib import Path

from app.services.discovery_core import assert_summary_safe
from app.services.local_repo_discovery import discover_local_repo, render_local_repo_audit
from scripts.run_local_repo_discovery import run

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fake_repo(root: Path) -> None:
    services = root / "app" / "services"
    services.mkdir(parents=True)
    for name in (
        "__init__.py",
        "jira_discovery.py",
        "github_discovery.py",
        "write_action_guard.py",
        "knowledge_graph.py",
        "second_opinion.py",
        "status_engine.py",
        "digest.py",
        "source_ingestion.py",
    ):
        (services / name).write_text("# stub\n")
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("# a\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")


def test_categorizes_service_modules(tmp_path) -> None:
    _fake_repo(tmp_path)
    summary = discover_local_repo(tmp_path)
    cats = summary["categories"]
    assert "jira_discovery" in cats["connectors_and_discovery"]
    assert "github_discovery" in cats["connectors_and_discovery"]
    assert "write_action_guard" in cats["guards_and_safety"]
    assert "knowledge_graph" in cats["graph_and_findings"]
    assert "second_opinion" in cats["graph_and_findings"]
    assert "status_engine" in cats["status_and_state"]
    assert "digest" in cats["digest_and_delivery"]
    # __init__ is excluded from the module count.
    assert summary["service_module_count"] == 8


def test_structure_counts_areas(tmp_path) -> None:
    _fake_repo(tmp_path)
    summary = discover_local_repo(tmp_path)
    assert summary["structure"]["app/services"] == 9  # includes __init__.py
    assert summary["structure"]["docs"] == 1
    assert summary["structure"]["tests"] == 1


def test_audit_renders(tmp_path) -> None:
    _fake_repo(tmp_path)
    md = render_local_repo_audit(discover_local_repo(tmp_path))
    assert "Local Repo Audit" in md
    assert "source-agent contract" in md.lower()


def test_run_writes_local_files_and_safe_stdout(tmp_path) -> None:
    _fake_repo(tmp_path)
    result = run(root=tmp_path, timestamp="20260615T000000Z")
    assert result["status"] == "ok"
    assert assert_summary_safe(result) == result
    run_root = tmp_path / ".local" / "discovery" / "local-repo" / "20260615T000000Z"
    assert (run_root / "summary.json").exists()
    assert (run_root / "local-repo-audit.md").exists()
    for artifact in result["artifacts"]:
        assert artifact["relative_path"].startswith(".local/discovery/local-repo/")


def test_real_repo_reference_modules_present() -> None:
    # Sanity check against the actual repo: the canonical source-agent modules
    # we built this session are detected.
    summary = discover_local_repo(REPO_ROOT)
    reference = summary["source_agent_pattern_reference"]
    assert reference["app/services/jira_discovery.py"] is True
    assert reference["app/services/write_action_guard.py"] is True
    assert summary["service_module_count"] > 90
