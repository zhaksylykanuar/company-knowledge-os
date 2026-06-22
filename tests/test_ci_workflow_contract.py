import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_ACTION_RE = re.compile(
    r"^\s*uses:\s+(?P<action>[^@\s]+)@(?P<ref>[0-9a-f]{40})\s+#\s+(?P<tag>\S+)",
    re.MULTILINE,
)
UNPINNED_ACTION_RE = re.compile(
    r"^\s*uses:\s+[^@\s]+@(?![0-9a-f]{40}\s+#\s+\S+)(?P<ref>\S+)",
    re.MULTILINE,
)
UNPINNED_CONTAINER_IMAGE_RE = re.compile(
    r"^\s*image:\s+(?P<image>[^@\s#]+)(?:\s+#.*)?$",
    re.MULTILINE,
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ci_uses_least_privilege_token_and_pinned_python() -> None:
    workflow = _text(".github/workflows/ci.yml")

    assert "\npermissions:\n  contents: read\n" in workflow
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7" in workflow
    assert (
        "postgres:16@sha256:081f1bc7bd5e143dbb6e487b710bbc27712cdcfaced4c071b8e47349aa1b4171"
        in workflow
    )
    assert "persist-credentials: false" in workflow
    assert "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0" in workflow
    assert "python-version-file: .python-version" in workflow
    assert "uv sync --frozen" in workflow
    assert "uv run alembic upgrade head" in workflow
    assert "bash scripts/check_no_secrets.sh --tracked" in workflow
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_codeql_scans_python_and_github_actions_with_v4() -> None:
    workflow = _text(".github/workflows/codeql.yml")

    assert "github/codeql-action/init@411bbbe57033eedfc1a82d68c01345aa96c737d7 # v4" in workflow
    assert "github/codeql-action/analyze@411bbbe57033eedfc1a82d68c01345aa96c737d7 # v4" in workflow
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7" in workflow
    assert "persist-credentials: false" in workflow
    assert "contents: read" in workflow
    assert "pull-requests: read" in workflow
    assert "security-events: write" in workflow
    assert "language: [python, actions]" in workflow
    assert "queries: security-and-quality" in workflow
    assert "schedule:" in workflow
    assert "pull_request:" in workflow


def test_openssf_scorecard_uploads_private_sarif_without_external_publish() -> None:
    workflow = _text(".github/workflows/scorecard.yml")

    assert "ossf/scorecard-action@99c09fe975337306107572b4fdf4db224cf8e2f2 # v2.4.3" in workflow
    assert "github/codeql-action/upload-sarif@411bbbe57033eedfc1a82d68c01345aa96c737d7 # v4" in workflow
    assert "results_format: sarif" in workflow
    assert "publish_results: false" in workflow
    assert "security-events: write" in workflow
    assert "id-token: write" not in workflow
    assert "pull_request:" not in workflow
    assert "persist-credentials: false" in workflow
    assert "schedule:" in workflow


def test_dependency_review_blocks_vulnerable_pr_dependency_changes() -> None:
    workflow = _text(".github/workflows/dependency-review.yml")

    assert "pull_request:" in workflow
    assert "pull_request_target" not in workflow
    assert "contents: read" in workflow
    assert "pull-requests: read" in workflow
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7" in workflow
    assert "persist-credentials: false" in workflow
    assert (
        "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294 # v5.0.0"
        in workflow
    )
    assert "fail-on-severity: high" in workflow
    assert "fail-on-scopes: runtime, development, unknown" in workflow
    assert "vulnerability-check: true" in workflow
    assert "license-check: true" in workflow
    assert "comment-summary-in-pr: never" in workflow
    assert "show-openssf-scorecard: true" in workflow
    assert "pull-requests: write" not in workflow


def test_uv_dependency_submission_publishes_uv_lock_graph_on_main_only() -> None:
    workflow = _text(".github/workflows/uv-dependency-submission.yml")

    assert "workflow_dispatch:" in workflow
    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert '"uv.lock"' in workflow
    assert '"**/uv.lock"' in workflow
    assert "pull_request" not in workflow
    assert "pull_request_target" not in workflow
    assert "\npermissions: {}\n" in workflow
    assert "contents: write" in workflow
    assert "id-token: write" not in workflow
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7" in workflow
    assert "persist-credentials: false" in workflow
    assert (
        "rmuir/uv-dependency-submission@8c650a3e5e519b93e604e644f7a4a3953144babe # v1.1.1"
        in workflow
    )


def test_github_workflow_actions_are_pinned_by_full_sha_with_tag_comments() -> None:
    workflow_paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflow_paths

    unpinned: list[str] = []
    pinned: list[str] = []
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for match in UNPINNED_ACTION_RE.finditer(text):
            unpinned.append(f"{rel}:{match.group('ref')}")
        for match in PINNED_ACTION_RE.finditer(text):
            pinned.append(
                f"{rel}:{match.group('action')}@{match.group('ref')} # {match.group('tag')}"
            )

    assert not unpinned
    assert pinned


def test_github_workflow_container_images_are_pinned_by_digest() -> None:
    workflow_paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflow_paths

    unpinned: list[str] = []
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for match in UNPINNED_CONTAINER_IMAGE_RE.finditer(text):
            unpinned.append(f"{rel}:{match.group('image')}")

    assert unpinned == []


def test_dependabot_tracks_github_actions() -> None:
    dependabot = _text(".github/dependabot.yml")

    assert 'package-ecosystem: "github-actions"' in dependabot
    assert 'directory: "/"' in dependabot
    assert 'interval: "weekly"' in dependabot


def test_renovate_tracks_uv_python_dependencies_without_action_duplicates() -> None:
    renovate = json.loads(_text("renovate.json"))

    assert renovate["$schema"] == "https://docs.renovatebot.com/renovate-schema.json"
    assert renovate["enabledManagers"] == ["pep621"]
    assert renovate["dependencyDashboard"] is True
    assert renovate["rangeStrategy"] == "bump"
    assert renovate["lockFileMaintenance"] == {
        "enabled": True,
        "schedule": ["before 6am on monday"],
    }
    assert "uv" in renovate["labels"]

    package_rule = renovate["packageRules"][0]
    assert package_rule["matchManagers"] == ["pep621"]
    assert package_rule["matchDatasources"] == ["pypi"]
    assert package_rule["minimumReleaseAge"] == "3 days"
    assert "github-actions" not in json.dumps(renovate)


def test_docs_include_quick_and_ci_parity_checks() -> None:
    readme = _text("README.md")
    playbook = _text("docs/playbook.md")

    assert "Quick local checks" in readme
    assert "CI parity before opening a PR" in readme
    assert "Dependency automation" in readme
    assert "Renovate" in readme
    assert "uv.lock" in readme
    assert "OpenSSF Scorecard" in readme
    assert "Dependency Review" in readme
    assert "uv Dependency Submission" in readme
    assert "uv.lock transitive coverage" in readme
    assert "manual SHA rotation" in readme
    assert "uv sync --frozen" in readme
    assert "uv run alembic upgrade head" in readme
    assert "tracked-secret scan" in playbook
