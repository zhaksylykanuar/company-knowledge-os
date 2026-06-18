"""Read-only GitHub discovery: GET-only org/repo facts.

Builds a factual picture of the current GitHub org and its repo(s) to inform the
repo ↔ Jira project/component mapping and the future-repo migration model. Hard
rules, same as Jira discovery:

- **GET only.** Transport is ``(method, path, params) -> json``; the real
  transport refuses any non-GET method. No write path exists here.
- **Secret-scrubbed saves.** README/content text is run through
  :func:`app.services.secret_patterns` redaction before being written locally.
- **Bounded.** Repo count, branches, and per-repo lists are capped.

Full data is written to local files by the caller; only sanitized counts and
classes reach stdout/chat.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.secret_patterns import contains_secret_value

GET = "GET"

REDACTED = "<redacted-secret>"
README_CHAR_CAP = 8000
MAX_REPOS = 50
MAX_BRANCHES = 200
MAX_PER_PAGE = 100
FUTURE_REPO_SLOTS = 19

FETCH_OK = "ok"
FETCH_FORBIDDEN = "forbidden_or_unavailable"

# filename -> ecosystem hint (root-level package/manifest files).
_PACKAGE_HINTS = {
    "package.json": "node",
    "pnpm-lock.yaml": "node",
    "yarn.lock": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "go.mod": "go",
    "cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "gemfile": "ruby",
    "composer.json": "php",
    "dockerfile": "containerized",
    "docker-compose.yml": "containerized",
}

GitHubTransport = Callable[[str, str, Mapping[str, Any]], Any]


class GitHubDiscoveryTransportError(RuntimeError):
    """Raised by a real transport if a non-GET method is ever attempted."""


@dataclass
class GitHubDiscoveryRaw:
    endpoint_status: dict[str, str] = field(default_factory=dict)
    organization: dict[str, Any] = field(default_factory=dict)
    repos: list[dict[str, Any]] = field(default_factory=list)


class GitHubReadOnlyDiscoveryClient:
    """GET-only GitHub REST client for discovery."""

    def __init__(self, transport: GitHubTransport, *, org: str, page_cap: int = 10):
        self._transport = transport
        self._org = "".join(c for c in str(org) if c.isalnum() or c in {"-", "_", "."})
        self._page_cap = max(1, int(page_cap))

    @property
    def org(self) -> str:
        return self._org

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._transport(GET, path, dict(params or {}))

    def organization(self) -> dict[str, Any]:
        data = self._get(f"/orgs/{self._org}")
        return dict(data) if isinstance(data, Mapping) else {}

    def org_repos(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for page in range(1, self._page_cap + 1):
            data = self._get(
                f"/orgs/{self._org}/repos",
                {"per_page": MAX_PER_PAGE, "page": page, "type": "all", "sort": "updated"},
            )
            chunk = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
            out.extend(chunk)
            if len(chunk) < MAX_PER_PAGE or len(out) >= MAX_REPOS:
                break
        return out[:MAX_REPOS]

    def readme(self, full_name: str) -> str:
        data = self._get(f"/repos/{full_name}/readme")
        if not isinstance(data, Mapping):
            return ""
        content = data.get("content")
        if not isinstance(content, str):
            return ""
        try:
            decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
        except (ValueError, TypeError):
            return ""
        return decoded[:README_CHAR_CAP]

    def root_contents(self, full_name: str) -> list[dict[str, Any]]:
        data = self._get(f"/repos/{full_name}/contents")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def branches(self, full_name: str) -> list[dict[str, Any]]:
        data = self._get(f"/repos/{full_name}/branches", {"per_page": MAX_PER_PAGE})
        rows = [b for b in data if isinstance(b, dict)] if isinstance(data, list) else []
        return rows[:MAX_BRANCHES]

    def languages(self, full_name: str) -> dict[str, Any]:
        data = self._get(f"/repos/{full_name}/languages")
        return dict(data) if isinstance(data, Mapping) else {}

    def recent_commits(self, full_name: str) -> list[dict[str, Any]]:
        data = self._get(f"/repos/{full_name}/commits", {"per_page": 30})
        return [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []

    def open_pull_requests(self, full_name: str) -> list[dict[str, Any]]:
        data = self._get(f"/repos/{full_name}/pulls", {"state": "open", "per_page": MAX_PER_PAGE})
        return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []


def collect_github_discovery(client: GitHubReadOnlyDiscoveryClient) -> GitHubDiscoveryRaw:
    raw = GitHubDiscoveryRaw()
    raw.organization = _safe(raw, "organization", client.organization, default={})
    repos = _safe(raw, "repos", client.org_repos, default=[])

    enriched: list[dict[str, Any]] = []
    for repo in repos or []:
        full_name = repo.get("full_name") or f"{client.org}/{repo.get('name', '')}"
        detail = dict(repo)
        detail["_readme"] = _try(lambda: client.readme(full_name), "")
        detail["_root_contents"] = _try(lambda: client.root_contents(full_name), [])
        detail["_branches"] = _try(lambda: client.branches(full_name), [])
        detail["_languages"] = _try(lambda: client.languages(full_name), {})
        detail["_recent_commits"] = _try(lambda: client.recent_commits(full_name), [])
        detail["_open_pull_requests"] = _try(lambda: client.open_pull_requests(full_name), [])
        enriched.append(detail)
    raw.repos = enriched
    return raw


def _safe(raw: GitHubDiscoveryRaw, label: str, fetch: Callable[[], Any], *, default: Any):
    try:
        result = fetch()
        raw.endpoint_status[label] = FETCH_OK
        return result
    except Exception:
        raw.endpoint_status[label] = FETCH_FORBIDDEN
        return default


def _try(fetch: Callable[[], Any], default: Any) -> Any:
    try:
        return fetch()
    except Exception:
        return default


def summarize_github_discovery(raw: GitHubDiscoveryRaw) -> dict[str, Any]:
    repos_summary = [_repo_summary(repo) for repo in raw.repos]
    return {
        "report_kind": "github_discovery_summary",
        "endpoint_status": dict(raw.endpoint_status),
        "organization": {
            "login": raw.organization.get("login", ""),
            "public_repos": raw.organization.get("public_repos", 0),
            "total_private_repos": raw.organization.get("total_private_repos", 0),
        },
        "counts": {
            "repo_count": len(raw.repos),
        },
        "repos": repos_summary,
        "future_repos_model": _future_repos_model(),
    }


def _repo_summary(repo: Mapping[str, Any]) -> dict[str, Any]:
    languages = repo.get("_languages") if isinstance(repo.get("_languages"), Mapping) else {}
    contents = repo.get("_root_contents") if isinstance(repo.get("_root_contents"), list) else []
    branches = repo.get("_branches") if isinstance(repo.get("_branches"), list) else []
    package_managers = _detect_package_managers(contents)
    return {
        "name": repo.get("name", ""),
        "default_branch": repo.get("default_branch", ""),
        "private": bool(repo.get("private", False)),
        "archived": bool(repo.get("archived", False)),
        "primary_language": repo.get("language") or _top_language(languages),
        "language_count": len(languages),
        "branch_count": len(branches),
        "open_issues": repo.get("open_issues_count", 0),
        "open_pull_request_count": len(repo.get("_open_pull_requests") or []),
        "topics": [t for t in (repo.get("topics") or []) if isinstance(t, str)][:20],
        "has_readme": bool(repo.get("_readme")),
        "package_managers": package_managers,
        "recent_commit_count": len(repo.get("_recent_commits") or []),
        "domain_hints": _domain_hints(repo, package_managers, languages),
    }


def _detect_package_managers(contents: Sequence[Mapping[str, Any]]) -> list[str]:
    found: list[str] = []
    for item in contents:
        name = str(item.get("name", "")).casefold()
        hint = _PACKAGE_HINTS.get(name)
        if hint and hint not in found:
            found.append(hint)
    return found


def _top_language(languages: Mapping[str, Any]) -> str:
    numeric = {k: v for k, v in languages.items() if isinstance(v, (int, float))}
    return max(numeric, key=numeric.get) if numeric else ""


def _domain_hints(
    repo: Mapping[str, Any],
    package_managers: Sequence[str],
    languages: Mapping[str, Any],
) -> list[str]:
    hints: list[str] = []
    name = str(repo.get("name", "")).casefold()
    for token, hint in (
        ("web", "frontend"),
        ("ui", "frontend"),
        ("front", "frontend"),
        ("api", "backend"),
        ("backend", "backend"),
        ("service", "service"),
        ("infra", "infrastructure"),
        ("data", "data"),
        ("mobile", "mobile"),
        ("ml", "rnd"),
        ("ai", "rnd"),
    ):
        if token in name and hint not in hints:
            hints.append(hint)
    if "node" in package_managers and "frontend" not in hints and "backend" not in hints:
        hints.append("node_app")
    if "python" in package_managers and "backend" not in hints:
        hints.append("python_app")
    return hints


def _future_repos_model() -> dict[str, Any]:
    return {
        "expected_additional_repos": FUTURE_REPO_SLOTS,
        "mapping_rule": "repo_as_component: each repo maps to one component in its owning area project",
        "status": "pending_migration",
        "slots": [
            {
                "slot": index,
                "owning_area": "to_decide_from_discovery",
                "component_name": "to_decide",
                "status": "not_yet_in_org",
            }
            for index in range(1, FUTURE_REPO_SLOTS + 1)
        ],
    }


def render_github_repo_audit(summary: Mapping[str, Any]) -> str:
    org = summary.get("organization", {})
    counts = summary.get("counts", {})
    repos = summary.get("repos", [])
    lines = [
        "# GitHub Repo Audit (read-only discovery)",
        "",
        "Generated by `scripts/run_github_discovery.py`. Read-only, GET-only.",
        "Input for `repo-to-jira-mapping.md` and the future-repo migration model.",
        "",
        "## Organization",
        "",
        f"- Login: {org.get('login', '')}",
        f"- Public repos: {org.get('public_repos', 0)}",
        f"- Repos discovered: {counts.get('repo_count', 0)}",
        "",
        "## Repositories",
        "",
    ]
    for repo in repos:
        lines += [
            f"### {repo.get('name', '')}",
            "",
            f"- Default branch: {repo.get('default_branch', '')}",
            f"- Primary language: {repo.get('primary_language', '')}",
            f"- Branches: {repo.get('branch_count', 0)}",
            f"- Open issues: {repo.get('open_issues', 0)} / open PRs: {repo.get('open_pull_request_count', 0)}",
            f"- Package managers: {', '.join(repo.get('package_managers', [])) or 'none detected'}",
            f"- Domain hints: {', '.join(repo.get('domain_hints', [])) or 'none'}",
            f"- README present: {repo.get('has_readme', False)}",
            "",
        ]
    future = summary.get("future_repos_model", {})
    lines += [
        "## Future repositories (placeholder model)",
        "",
        f"- Expected additional repos: {future.get('expected_additional_repos', 0)}",
        f"- Mapping rule: {future.get('mapping_rule', '')}",
        "- Each slot's owning area/component is a founder decision filled during migration.",
        "",
        "Raw responses are in the sibling `raw/` directory (local only).",
        "",
    ]
    return "\n".join(lines)


def scrub_for_save(value: Any) -> Any:
    """Recursively redact secret-bearing strings before saving locally."""
    if isinstance(value, str):
        return REDACTED if contains_secret_value(value) else value
    if isinstance(value, Mapping):
        return {key: scrub_for_save(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_for_save(item) for item in value]
    return value


def stdout_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Numeric/class-only view safe for stdout — no repo names or topics."""
    repos = summary.get("repos", [])
    return {
        "endpoint_status": summary.get("endpoint_status", {}),
        "counts": summary.get("counts", {}),
        "repo_metrics": {
            "with_readme": sum(1 for r in repos if r.get("has_readme")),
            "archived": sum(1 for r in repos if r.get("archived")),
            "private": sum(1 for r in repos if r.get("private")),
            "total_open_issues": sum(int(r.get("open_issues", 0) or 0) for r in repos),
            "total_open_prs": sum(int(r.get("open_pull_request_count", 0) or 0) for r in repos),
        },
        "future_repos_expected": summary.get("future_repos_model", {}).get(
            "expected_additional_repos", 0
        ),
    }
