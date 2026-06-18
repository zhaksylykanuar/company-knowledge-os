"""Read-only GitHub discovery: GET-only, fail-closed, no network, no leaks."""

from __future__ import annotations

import base64
import json

import pytest

from app.services.discovery_core import assert_summary_safe
from app.services.github_discovery import (
    GitHubDiscoveryTransportError,
    GitHubReadOnlyDiscoveryClient,
    collect_github_discovery,
    scrub_for_save,
    summarize_github_discovery,
)
from app.services.secret_patterns import contains_secret_value
from scripts.run_github_discovery import (
    CONFIRM_TOKEN,
    STATUS_CREDENTIALS_MISSING,
    STATUS_OK,
    STATUS_PREFLIGHT_ONLY,
    _http_get_transport,
    run,
)

_ORG = "example-org"
_REPO = "repo-alpha-web"
_FULL = f"{_ORG}/{_REPO}"


def _routes() -> dict[str, object]:
    return {
        f"/orgs/{_ORG}/repos": [
            {
                "full_name": _FULL,
                "name": _REPO,
                "default_branch": "main",
                "language": "TypeScript",
                "open_issues_count": 3,
                "topics": ["frontend"],
                "private": False,
                "archived": False,
            }
        ],
        f"/orgs/{_ORG}": {"login": _ORG, "public_repos": 1},
        f"/repos/{_FULL}/readme": {
            "content": base64.b64encode(b"# Project Alpha Web\n").decode(),
            "encoding": "base64",
        },
        f"/repos/{_FULL}/contents": [
            {"name": "package.json", "type": "file"},
            {"name": "Dockerfile", "type": "file"},
        ],
        f"/repos/{_FULL}/branches": [{"name": "main"}, {"name": "dev"}],
        f"/repos/{_FULL}/languages": {"TypeScript": 1000, "CSS": 100},
        f"/repos/{_FULL}/commits": [{"sha": "abc"}, {"sha": "def"}],
        f"/repos/{_FULL}/pulls": [{"id": 1}],
    }


def _fake_transport(routes=None, recorder=None):
    table = routes if routes is not None else _routes()

    def transport(method, path, params):
        if recorder is not None:
            recorder.append((method, path))
        # Most specific match first.
        for prefix in sorted(table, key=len, reverse=True):
            if path.startswith(prefix):
                return table[prefix]
        return {}

    return transport


def _factory(**kwargs):
    return lambda env: _fake_transport(**kwargs)


def _github_env():
    return {
        "FOS_GITHUB_READONLY_TOKEN": "ghp_" + "y" * 36,
        "FOS_GITHUB_TARGET_ORG": _ORG,
    }


def _client(**kwargs):
    return GitHubReadOnlyDiscoveryClient(_fake_transport(**kwargs), org=_ORG)


def test_client_issues_only_get_requests() -> None:
    recorder: list = []
    collect_github_discovery(_client(recorder=recorder))
    assert recorder
    assert all(method == "GET" for method, _ in recorder)


def test_summary_repo_facts_and_domain_hints() -> None:
    summary = summarize_github_discovery(collect_github_discovery(_client()))
    assert summary["counts"]["repo_count"] == 1
    repo = summary["repos"][0]
    assert repo["name"] == _REPO
    assert repo["primary_language"] == "TypeScript"
    assert repo["branch_count"] == 2
    assert repo["has_readme"] is True
    assert "node" in repo["package_managers"]
    assert "containerized" in repo["package_managers"]
    assert "frontend" in repo["domain_hints"]


def test_future_repos_model_present() -> None:
    summary = summarize_github_discovery(collect_github_discovery(_client()))
    future = summary["future_repos_model"]
    assert future["expected_additional_repos"] == 19
    assert len(future["slots"]) == 19


def test_scrub_redacts_secret_in_readme() -> None:
    scrubbed = scrub_for_save({"_readme": "token ghp_" + "a" * 36, "name": _REPO})
    assert "ghp_" not in json.dumps(scrubbed)
    assert scrubbed["name"] == _REPO


def test_run_without_confirm_makes_no_network_call(tmp_path) -> None:
    def exploding_factory(env):
        raise AssertionError("no network in preflight")

    result = run(
        confirm_run=None,
        root=tmp_path,
        environ=_github_env(),
        transport_factory=exploding_factory,
    )
    assert result["status"] == STATUS_PREFLIGHT_ONLY
    assert result["credentials"]["ready"] is True


def test_run_missing_creds_makes_no_network_call(tmp_path) -> None:
    def exploding_factory(env):
        raise AssertionError("no network without creds")

    result = run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ={"FOS_GITHUB_TARGET_ORG": _ORG},
        transport_factory=exploding_factory,
    )
    assert result["status"] == STATUS_CREDENTIALS_MISSING
    assert "FOS_GITHUB_READONLY_TOKEN" in result["credentials"]["missing_var_names"]


def test_run_confirmed_writes_local_files_and_safe_stdout(tmp_path) -> None:
    result = run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ=_github_env(),
        timestamp="20260615T000000Z",
        transport_factory=_factory(),
    )
    assert result["status"] == STATUS_OK
    assert assert_summary_safe(result) == result
    blob = json.dumps(result)
    # stdout carries no repo names or topics.
    assert _REPO not in blob
    run_root = tmp_path / ".local" / "discovery" / "github" / "20260615T000000Z"
    assert (run_root / "raw" / "repos.json").exists()
    assert (run_root / "summary.json").exists()
    assert (run_root / "github-repo-audit.md").exists()
    for artifact in result["artifacts"]:
        assert artifact["relative_path"].startswith(".local/discovery/github/")
        assert ".." not in artifact["relative_path"]


def test_run_redacts_secret_in_saved_raw(tmp_path) -> None:
    leaky = _routes()
    leaky[f"/repos/{_FULL}/readme"] = {
        "content": base64.b64encode(b"deploy token ghp_" + b"z" * 36).decode(),
        "encoding": "base64",
    }
    run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ=_github_env(),
        timestamp="20260615T000000Z",
        transport_factory=_factory(routes=leaky),
    )
    saved = (
        tmp_path / ".local" / "discovery" / "github" / "20260615T000000Z" / "raw" / "repos.json"
    ).read_text()
    assert "ghp_" not in saved
    assert not contains_secret_value(saved)


def test_real_transport_refuses_non_get() -> None:
    transport = _http_get_transport(_github_env())
    with pytest.raises(GitHubDiscoveryTransportError):
        transport("POST", "/repos/x/y/issues", {})
    with pytest.raises(GitHubDiscoveryTransportError):
        transport("PATCH", "/repos/x/y", {})
