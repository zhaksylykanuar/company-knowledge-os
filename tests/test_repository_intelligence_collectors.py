from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import subprocess
from uuid import UUID, uuid4

import pytest

from app.services.repository_intelligence.checkout import (
    RepositoryCheckoutPolicy,
    RepositoryCheckoutRequest,
    materialize_repository_checkout,
)
from app.services.repository_intelligence.collectors import (
    RepositoryStaticCollectionLimitError,
    RepositoryStaticCollectorPolicy,
    collect_repository_static_facts,
    validate_repository_static_collection_json,
)
from app.services.repository_intelligence.contracts import RepositoryClaimV1


WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")
REPOSITORY_ID = UUID("22222222-2222-4222-8222-222222222222")


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Synthetic Fixture",
            "GIT_AUTHOR_EMAIL": "synthetic@example.test",
            "GIT_COMMITTER_NAME": "Synthetic Fixture",
            "GIT_COMMITTER_EMAIL": "synthetic@example.test",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _repository(path: Path, files: dict[str, str]) -> tuple[Path, str]:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    for relative, content in files.items():
        destination = path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    _git(path, "add", "--all")
    _git(path, "commit", "-q", "-m", "synthetic collector fixture")
    return path.resolve(), _git(path, "rev-parse", "HEAD")


def _checkout_policy(data_path: Path) -> RepositoryCheckoutPolicy:
    return RepositoryCheckoutPolicy(
        data_path=data_path,
        timeout_seconds=5.0,
        max_files=200,
        max_bytes=4 * 1024 * 1024,
        max_file_bytes=512 * 1024,
        max_command_output_bytes=4 * 1024 * 1024,
        max_path_bytes=512,
        max_depth=32,
    )


def _collect(
    repository: Path,
    sha: str,
    data_path: Path,
    *,
    full_name: str,
    policy: RepositoryStaticCollectorPolicy | None = None,
):
    request = RepositoryCheckoutRequest(
        source_repository=repository,
        commit_sha=sha,
        run_id=f"collector-{uuid4().hex[:12]}",
    )
    with materialize_repository_checkout(
        request,
        policy=_checkout_policy(data_path),
    ) as checkout:
        result = collect_repository_static_facts(
            checkout,
            workspace_id=WORKSPACE_ID,
            repository_id=REPOSITORY_ID,
            repository_full_name=full_name,
            policy=policy,
        )
        assert checkout.path.exists()
    assert not checkout.path.exists()
    return result


def _fact_values(result, section: str) -> set[tuple[str, str]]:
    return {
        (fact.fact_type, fact.value)
        for fact in getattr(result, section)
    }


def test_frontend_fixture_collects_deterministic_static_facts(tmp_path: Path) -> None:
    repository, sha = _repository(
        tmp_path / "frontend",
        {
            "package.json": (
                '{"name":"synthetic-portal","private":true,'
                '"dependencies":{"next":"15.0.0","react":"19.0.0"},'
                '"devDependencies":{"vitest":"2.0.0"},'
                '"scripts":{"test":"touch should-not-exist"},'
                '"main":"src/index.ts"}'
            ),
            "src/pages/index.tsx": "export default function Home(){return null}\n",
            "openapi.yaml": "openapi: 3.1.0\ninfo:\n  title: Synthetic API\n",
            ".github/workflows/ci.yml": "on: [push]\njobs: {}\n",
            "tests/home.test.ts": "throw new Error('never executed')\n",
            "README.md": "# Synthetic Portal\n",
            "Dockerfile": "FROM scratch\n",
        },
    )

    first = _collect(
        repository,
        sha,
        tmp_path / "runtime-one",
        full_name="synthetic-company/frontend",
    )
    second = _collect(
        repository,
        sha,
        tmp_path / "runtime-two",
        full_name="synthetic-company/frontend",
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert (
        validate_repository_static_collection_json(first.deterministic_json())
        == first
    )
    assert ("node_manifest", "package.json") in _fact_values(first, "manifests")
    assert {
        ("package_dependency", "next"),
        ("package_dependency", "react"),
        ("package_dependency", "vitest"),
    }.issubset(_fact_values(first, "dependencies"))
    assert ("source_entrypoint", "src/pages/index.tsx") in _fact_values(
        first,
        "entrypoints",
    )
    assert ("openapi_contract", "openapi.yaml") in _fact_values(first, "interfaces")
    assert ("container_build", "Dockerfile") in _fact_values(first, "deployment")
    assert ("ci_workflow", ".github/workflows/ci.yml") in _fact_values(
        first,
        "tests_ci",
    )
    assert ("documentation_file", "README.md") in _fact_values(
        first,
        "documentation",
    )
    assert first.target_code_executed is False
    assert first.network_used is False
    assert not (repository / "should-not-exist").exists()


def test_backend_fixture_collects_routes_dependencies_and_migrations(
    tmp_path: Path,
) -> None:
    repository, sha = _repository(
        tmp_path / "backend",
        {
            "pyproject.toml": (
                '[project]\nname = "synthetic-service"\n'
                'dependencies = ["fastapi>=0.115", "asyncpg>=0.29"]\n'
                '[project.scripts]\nsynthetic = "app.main:main"\n'
            ),
            "app/main.py": (
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                '@app.get("/health")\n'
                "def health(): return {'ok': True}\n"
                "if __name__ == '__main__':\n"
                "    raise RuntimeError('never executed')\n"
            ),
            "migrations/001_create_orders.sql": (
                "CREATE TABLE orders (id bigint primary key);\n"
            ),
            "tests/test_health.py": "raise RuntimeError('never executed')\n",
            "docs/architecture.md": "# Architecture\n",
        },
    )

    result = _collect(
        repository,
        sha,
        tmp_path / "runtime",
        full_name="synthetic-company/backend",
    )

    assert {
        ("package_dependency", "asyncpg"),
        ("package_dependency", "fastapi"),
    }.issubset(_fact_values(result, "dependencies"))
    assert ("manifest_entrypoint", "app.main:main") in _fact_values(
        result,
        "entrypoints",
    )
    assert ("source_entrypoint", "app/main.py") in _fact_values(
        result,
        "entrypoints",
    )
    assert ("http_route", "/health") in _fact_values(result, "interfaces")
    assert ("migration_file", "migrations/001_create_orders.sql") in _fact_values(
        result,
        "migrations",
    )
    assert ("database_object", "orders") in _fact_values(result, "migrations")
    assert ("architecture_document", "docs/architecture.md") in _fact_values(
        result,
        "documentation",
    )
    assert all(isinstance(claim, RepositoryClaimV1) for claim in result.analyzer_claims())
    assert not (repository / "never-executed").exists()


def test_infrastructure_fixture_collects_deploy_ci_and_documentation(
    tmp_path: Path,
) -> None:
    repository, sha = _repository(
        tmp_path / "infrastructure",
        {
            "terraform/main.tf": 'resource "null_resource" "synthetic" {}\n',
            "helm/service/Chart.yaml": "apiVersion: v2\nname: synthetic-service\n",
            "helm/service/templates/deployment.yaml": "kind: Deployment\n",
            ".github/workflows/deploy.yml": "on:\n  workflow_dispatch:\njobs: {}\n",
            "docs/runbook.md": "# Synthetic Runbook\n",
        },
    )

    result = _collect(
        repository,
        sha,
        tmp_path / "runtime",
        full_name="synthetic-company/infrastructure",
    )

    assert ("terraform_definition", "terraform/main.tf") in _fact_values(
        result,
        "deployment",
    )
    assert ("helm_definition", "helm/service/Chart.yaml") in _fact_values(
        result,
        "deployment",
    )
    assert ("ci_workflow", ".github/workflows/deploy.yml") in _fact_values(
        result,
        "tests_ci",
    )
    assert ("documentation_file", "docs/runbook.md") in _fact_values(
        result,
        "documentation",
    )
    for fact in result.facts():
        material = fact.model_dump(mode="json")
        assert "resource " not in str(material)
        assert fact.evidence_ref.ref is not None
        assert fact.path in fact.evidence_ref.ref


def test_collector_bounds_large_recognized_files_without_exposing_content(
    tmp_path: Path,
) -> None:
    marker = "private-fixture-marker-that-must-not-appear"
    repository, sha = _repository(
        tmp_path / "bounded",
        {
            "package.json": '{"name":"bounded"}',
            "README.md": marker * 100,
        },
    )
    result = _collect(
        repository,
        sha,
        tmp_path / "runtime",
        full_name="synthetic-company/bounded",
        policy=RepositoryStaticCollectorPolicy(max_file_bytes=128),
    )

    assert result.skipped_files == 1
    assert marker not in result.model_dump_json()


def test_collector_fails_closed_on_file_and_output_bounds(tmp_path: Path) -> None:
    repository, sha = _repository(
        tmp_path / "pathological",
        {
            **{f"src/file-{index}.txt": "synthetic\n" for index in range(4)},
            "package.json": (
                '{"dependencies":{'
                + ",".join(f'"dep-{index}":"1"' for index in range(4))
                + "}}"
            ),
        },
    )
    request = RepositoryCheckoutRequest(
        source_repository=repository,
        commit_sha=sha,
        run_id="pathological-files",
    )
    with materialize_repository_checkout(
        request,
        policy=_checkout_policy(tmp_path / "runtime-files"),
    ) as checkout:
        with pytest.raises(RepositoryStaticCollectionLimitError):
            collect_repository_static_facts(
                checkout,
                workspace_id=WORKSPACE_ID,
                repository_id=REPOSITORY_ID,
                repository_full_name="synthetic-company/pathological",
                policy=RepositoryStaticCollectorPolicy(max_files=2),
            )

    with materialize_repository_checkout(
        replace(request, run_id="pathological-output"),
        policy=_checkout_policy(tmp_path / "runtime-output"),
    ) as checkout:
        with pytest.raises(RepositoryStaticCollectionLimitError):
            collect_repository_static_facts(
                checkout,
                workspace_id=WORKSPACE_ID,
                repository_id=REPOSITORY_ID,
                repository_full_name="synthetic-company/pathological",
                policy=RepositoryStaticCollectorPolicy(max_items_per_category=2),
            )

    with materialize_repository_checkout(
        replace(request, run_id="pathological-dependencies"),
        policy=_checkout_policy(tmp_path / "runtime-dependencies"),
    ) as checkout:
        with pytest.raises(RepositoryStaticCollectionLimitError):
            collect_repository_static_facts(
                checkout,
                workspace_id=WORKSPACE_ID,
                repository_id=REPOSITORY_ID,
                repository_full_name="synthetic-company/pathological",
                policy=RepositoryStaticCollectorPolicy(
                    max_dependencies_per_manifest=2
                ),
            )

    with materialize_repository_checkout(
        replace(request, run_id="pathological-total-items"),
        policy=_checkout_policy(tmp_path / "runtime-total-items"),
    ) as checkout:
        with pytest.raises(RepositoryStaticCollectionLimitError):
            collect_repository_static_facts(
                checkout,
                workspace_id=WORKSPACE_ID,
                repository_id=REPOSITORY_ID,
                repository_full_name="synthetic-company/pathological",
                policy=RepositoryStaticCollectorPolicy(max_total_items=2),
            )


def test_collector_source_contains_no_target_execution_or_network_path() -> None:
    import app.services.repository_intelligence.collectors as collectors_service

    source = Path(collectors_service.__file__).read_text(encoding="utf-8")
    forbidden = (
        "subprocess.",
        "os.system",
        "exec(",
        "eval(",
        "requests.",
        "httpx.",
        "urllib.request",
    )
    assert all(fragment not in source for fragment in forbidden)
