from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.repository_intelligence.collectors import (
    RepositoryStaticCollectionV1,
    RepositoryStaticFactV1,
)
from app.services.repository_intelligence.contracts import EvidenceRefV1
from app.services.repository_intelligence.relationships import (
    RepositoryPortfolioEntryV1,
    RepositoryPortfolioV1,
    RepositoryRelationshipLimitError,
    RepositoryRelationshipPolicy,
    RepositoryRelationshipSignalV1,
    RepositoryRelationshipValidationError,
    build_repository_relationship_analysis,
    validate_repository_relationship_analysis_json,
)
from app.services.repository_intelligence.taxonomy import (
    AnalyzerClaimStatus,
    EvidenceKind,
    EvidenceSource,
    RelationshipType,
)


WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")
FRONTEND_ID = UUID("22222222-2222-4222-8222-222222222222")
BACKEND_ID = UUID("33333333-3333-4333-8333-333333333333")
INFRA_ID = UUID("44444444-4444-4444-8444-444444444444")
ORPHAN_ID = UUID("55555555-5555-4555-8555-555555555555")


def _evidence(path: str, *, kind: EvidenceKind) -> EvidenceRefV1:
    return EvidenceRefV1(
        kind=kind,
        source=EvidenceSource.INTERNAL,
        ref=f"synthetic-company/source@{'a' * 40}:{path}",
    )


def _fact(
    *,
    fact_id: str,
    category: str,
    fact_type: str,
    value: str,
    path: str,
    kind: EvidenceKind,
) -> RepositoryStaticFactV1:
    return RepositoryStaticFactV1(
        fact_id=fact_id,
        category=category,
        fact_type=fact_type,
        value=value,
        path=path,
        evidence_ref=_evidence(path, kind=kind),
    )


def _collection(
    repository_id: UUID,
    *,
    dependencies: list[RepositoryStaticFactV1] | None = None,
    interfaces: list[RepositoryStaticFactV1] | None = None,
    deployment: list[RepositoryStaticFactV1] | None = None,
    tests_ci: list[RepositoryStaticFactV1] | None = None,
) -> RepositoryStaticCollectionV1:
    return RepositoryStaticCollectionV1(
        schema_version="repository_static_collection.v1",
        workspace_id=WORKSPACE_ID,
        repository_id=repository_id,
        commit_sha="a" * 40,
        dependencies=dependencies or [],
        interfaces=interfaces or [],
        deployment=deployment or [],
        tests_ci=tests_ci or [],
        files_considered=4,
        bytes_read=256,
        skipped_files=0,
        limitations=["Synthetic relationship fixture."],
    )


def _entry(
    *,
    repository_id: UUID,
    external_id: str,
    full_name: str,
    package_names: list[str] | None = None,
    api_contracts: list[str] | None = None,
    event_contracts: list[str] | None = None,
    image_names: list[str] | None = None,
    deployment_targets: list[str] | None = None,
) -> RepositoryPortfolioEntryV1:
    return RepositoryPortfolioEntryV1(
        workspace_id=WORKSPACE_ID,
        repository_id=repository_id,
        external_id=external_id,
        full_name=full_name,
        package_names=package_names or [],
        api_contracts=api_contracts or [],
        event_contracts=event_contracts or [],
        image_names=image_names or [],
        deployment_targets=deployment_targets or [],
    )


def _portfolio(*repositories: RepositoryPortfolioEntryV1) -> RepositoryPortfolioV1:
    return RepositoryPortfolioV1(
        schema_version="repository_portfolio.v1",
        workspace_id=WORKSPACE_ID,
        repositories=list(repositories),
    )


def _signal(
    *,
    source_id: UUID,
    relationship_type: RelationshipType,
    target: str,
    path: str,
    status: AnalyzerClaimStatus = AnalyzerClaimStatus.OBSERVED,
) -> RepositoryRelationshipSignalV1:
    return RepositoryRelationshipSignalV1(
        workspace_id=WORKSPACE_ID,
        from_repository_id=source_id,
        relationship_type=relationship_type,
        target_selector=target,
        evidence_refs=[
            _evidence(path, kind=EvidenceKind.REPOSITORY_DEPENDENCY)
        ],
        source_status=status,
    )


def test_static_facts_build_package_api_event_and_deploy_edges() -> None:
    frontend = _entry(
        repository_id=FRONTEND_ID,
        external_id="frontend-1",
        full_name="synthetic-company/frontend",
    )
    backend = _entry(
        repository_id=BACKEND_ID,
        external_id="backend-1",
        full_name="synthetic-company/backend",
        package_names=["@synthetic/orders-client"],
        api_contracts=["orders-api"],
        event_contracts=["orders.created"],
    )
    infrastructure = _entry(
        repository_id=INFRA_ID,
        external_id="infra-1",
        full_name="synthetic-company/infrastructure",
        deployment_targets=["orders-service"],
    )
    frontend_collection = _collection(
        FRONTEND_ID,
        dependencies=[
            _fact(
                fact_id="dependency.internal-package",
                category="dependency",
                fact_type="internal_package_dependency",
                value="@synthetic/orders-client",
                path="package.json",
                kind=EvidenceKind.REPOSITORY_DEPENDENCY,
            ),
            _fact(
                fact_id="dependency.api",
                category="dependency",
                fact_type="api_call_target",
                value="orders-api",
                path="src/api.ts",
                kind=EvidenceKind.REPOSITORY_SYMBOL,
            ),
            _fact(
                fact_id="dependency.event",
                category="dependency",
                fact_type="event_consumer",
                value="orders.created",
                path="src/events.ts",
                kind=EvidenceKind.REPOSITORY_SYMBOL,
            ),
        ],
    )
    infrastructure_collection = _collection(
        INFRA_ID,
        deployment=[
            _fact(
                fact_id="deployment.backend",
                category="deployment",
                fact_type="deployed_repository",
                value="backend-1",
                path="terraform/main.tf",
                kind=EvidenceKind.REPOSITORY_DEPLOYMENT,
            )
        ],
    )

    first = build_repository_relationship_analysis(
        portfolio=_portfolio(frontend, backend, infrastructure),
        collections=[frontend_collection, infrastructure_collection],
    )
    second = build_repository_relationship_analysis(
        portfolio=_portfolio(frontend, backend, infrastructure),
        collections=[infrastructure_collection, frontend_collection],
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert validate_repository_relationship_analysis_json(
        first.deterministic_json()
    ) == first
    edges = {
        (
            relationship.from_repository.repository_id,
            relationship.relationship_type,
            relationship.to_repository.repository_id,
        )
        for relationship in first.relationships
    }
    assert (
        FRONTEND_ID,
        RelationshipType.IMPORTS_PACKAGE_FROM,
        BACKEND_ID,
    ) in edges
    assert (FRONTEND_ID, RelationshipType.CALLS_API_OF, BACKEND_ID) in edges
    assert (
        FRONTEND_ID,
        RelationshipType.CONSUMES_EVENT_FROM,
        BACKEND_ID,
    ) in edges
    assert (
        INFRA_ID,
        RelationshipType.DEPLOYED_BY,
        BACKEND_ID,
    ) in edges
    assert all(relationship.evidence_refs for relationship in first.relationships)
    assert any("provides api to" in view for view in first.inverse_views)
    by_type = {
        relationship.relationship_type: relationship
        for relationship in first.relationships
    }
    assert (
        by_type[RelationshipType.IMPORTS_PACKAGE_FROM].status
        == AnalyzerClaimStatus.OBSERVED
    )
    assert (
        by_type[RelationshipType.IMPORTS_PACKAGE_FROM].human_resolution.status
        == "pending"
    )


def test_unresolved_targets_remain_candidates_and_name_similarity_is_ignored() -> None:
    source = _entry(
        repository_id=FRONTEND_ID,
        external_id="orders-ui",
        full_name="synthetic-company/orders-ui",
    )
    similarly_named = _entry(
        repository_id=BACKEND_ID,
        external_id="orders-api",
        full_name="synthetic-company/orders-api",
    )
    signal = _signal(
        source_id=FRONTEND_ID,
        relationship_type=RelationshipType.CALLS_API_OF,
        target="missing-service",
        path="src/client.ts",
    )

    result = build_repository_relationship_analysis(
        portfolio=_portfolio(source, similarly_named),
        signals=[signal],
    )

    [relationship] = result.relationships
    assert relationship.to_repository.repository_id is None
    assert relationship.to_repository.resolution_status.value == "candidate"
    assert result.unresolved_relationship_ids == [relationship.relationship_id]
    assert BACKEND_ID in result.orphan_repository_ids
    assert any(
        finding.finding_type == "unresolved_target"
        for finding in result.findings
    )


def test_symmetric_relationship_normalizes_and_merges_evidence() -> None:
    alpha = _entry(
        repository_id=FRONTEND_ID,
        external_id="alpha",
        full_name="synthetic-company/alpha",
    )
    beta = _entry(
        repository_id=BACKEND_ID,
        external_id="beta",
        full_name="synthetic-company/beta",
    )

    result = build_repository_relationship_analysis(
        portfolio=_portfolio(alpha, beta),
        signals=[
            _signal(
                source_id=BACKEND_ID,
                relationship_type=RelationshipType.SHARES_SCHEMA_WITH,
                target="alpha",
                path="schema/beta.graphql",
            ),
            _signal(
                source_id=FRONTEND_ID,
                relationship_type=RelationshipType.SHARES_SCHEMA_WITH,
                target="beta",
                path="schema/alpha.graphql",
                status=AnalyzerClaimStatus.INFERRED,
            ),
        ],
    )

    assert len(result.relationships) == 1
    [relationship] = result.relationships
    assert relationship.from_repository.external_id == "alpha"
    assert relationship.to_repository.external_id == "beta"
    assert relationship.status == AnalyzerClaimStatus.OBSERVED
    assert len(relationship.evidence_refs) == 2


def test_cycles_orphans_and_inverse_views_are_deterministic() -> None:
    alpha = _entry(
        repository_id=FRONTEND_ID,
        external_id="alpha",
        full_name="synthetic-company/alpha",
    )
    beta = _entry(
        repository_id=BACKEND_ID,
        external_id="beta",
        full_name="synthetic-company/beta",
    )
    gamma = _entry(
        repository_id=INFRA_ID,
        external_id="gamma",
        full_name="synthetic-company/gamma",
    )
    orphan = _entry(
        repository_id=ORPHAN_ID,
        external_id="orphan",
        full_name="synthetic-company/orphan",
    )
    result = build_repository_relationship_analysis(
        portfolio=_portfolio(alpha, beta, gamma, orphan),
        signals=[
            _signal(
                source_id=FRONTEND_ID,
                relationship_type=RelationshipType.CALLS_API_OF,
                target="beta",
                path="alpha.py",
            ),
            _signal(
                source_id=BACKEND_ID,
                relationship_type=RelationshipType.CALLS_API_OF,
                target="gamma",
                path="beta.py",
            ),
            _signal(
                source_id=INFRA_ID,
                relationship_type=RelationshipType.CALLS_API_OF,
                target="alpha",
                path="gamma.py",
            ),
        ],
    )

    assert result.cycles == [[FRONTEND_ID, BACKEND_ID, INFRA_ID]]
    assert result.orphan_repository_ids == [ORPHAN_ID]
    assert any(finding.finding_type == "cycle" for finding in result.findings)
    assert any(finding.finding_type == "orphan" for finding in result.findings)
    assert len(result.inverse_views) == 3


def test_opposing_directional_candidates_fail_as_contradiction() -> None:
    alpha = _entry(
        repository_id=FRONTEND_ID,
        external_id="alpha",
        full_name="synthetic-company/alpha",
    )
    beta = _entry(
        repository_id=BACKEND_ID,
        external_id="beta",
        full_name="synthetic-company/beta",
    )

    with pytest.raises(
        RepositoryRelationshipValidationError,
        match="contradiction review",
    ):
        build_repository_relationship_analysis(
            portfolio=_portfolio(alpha, beta),
            signals=[
                _signal(
                    source_id=FRONTEND_ID,
                    relationship_type=RelationshipType.CALLS_API_OF,
                    target="beta",
                    path="alpha.py",
                ),
                _signal(
                    source_id=BACKEND_ID,
                    relationship_type=RelationshipType.CALLS_API_OF,
                    target="alpha",
                    path="beta.py",
                ),
            ],
        )


def test_relationship_analysis_rejects_cross_workspace_self_edge_and_ambiguity() -> None:
    alpha = _entry(
        repository_id=FRONTEND_ID,
        external_id="alpha",
        full_name="synthetic-company/alpha",
        package_names=["duplicate-package"],
    )
    beta = _entry(
        repository_id=BACKEND_ID,
        external_id="beta",
        full_name="synthetic-company/beta",
        package_names=["duplicate-package"],
    )
    with pytest.raises(ValidationError):
        _portfolio(alpha, beta)

    portfolio = _portfolio(alpha)
    with pytest.raises(RepositoryRelationshipValidationError, match="self-edge"):
        build_repository_relationship_analysis(
            portfolio=portfolio,
            signals=[
                _signal(
                    source_id=FRONTEND_ID,
                    relationship_type=RelationshipType.CALLS_API_OF,
                    target="alpha",
                    path="alpha.py",
                )
            ],
        )

    foreign = _signal(
        source_id=FRONTEND_ID,
        relationship_type=RelationshipType.CALLS_API_OF,
        target="missing",
        path="alpha.py",
    ).model_copy(update={"workspace_id": UUID(int=9)})
    with pytest.raises(
        RepositoryRelationshipValidationError,
        match="cross portfolio workspaces",
    ):
        build_repository_relationship_analysis(
            portfolio=portfolio,
            signals=[foreign],
        )


def test_relationship_analysis_enforces_edge_cycle_finding_and_output_bounds() -> None:
    alpha = _entry(
        repository_id=FRONTEND_ID,
        external_id="alpha",
        full_name="synthetic-company/alpha",
    )
    beta = _entry(
        repository_id=BACKEND_ID,
        external_id="beta",
        full_name="synthetic-company/beta",
    )
    gamma = _entry(
        repository_id=INFRA_ID,
        external_id="gamma",
        full_name="synthetic-company/gamma",
    )
    signals = [
        _signal(
            source_id=FRONTEND_ID,
            relationship_type=RelationshipType.CALLS_API_OF,
            target="beta",
            path="alpha.py",
        ),
        _signal(
            source_id=FRONTEND_ID,
            relationship_type=RelationshipType.TESTS,
            target="gamma",
            path="tests.py",
        ),
    ]
    with pytest.raises(RepositoryRelationshipLimitError, match="edge bound"):
        build_repository_relationship_analysis(
            portfolio=_portfolio(alpha, beta, gamma),
            signals=signals,
            policy=RepositoryRelationshipPolicy(max_relationships=1),
        )
    with pytest.raises(RepositoryRelationshipLimitError, match="finding bound"):
        build_repository_relationship_analysis(
            portfolio=_portfolio(alpha, beta, gamma),
            signals=[],
            policy=RepositoryRelationshipPolicy(max_findings=1),
        )
    with pytest.raises(RepositoryRelationshipLimitError, match="output byte"):
        build_repository_relationship_analysis(
            portfolio=_portfolio(alpha, beta),
            signals=signals[:1],
            policy=RepositoryRelationshipPolicy(max_output_bytes=1024),
        )


def test_duplicate_collection_and_signal_input_bounds_fail_closed() -> None:
    alpha = _entry(
        repository_id=FRONTEND_ID,
        external_id="alpha",
        full_name="synthetic-company/alpha",
    )
    beta = _entry(
        repository_id=BACKEND_ID,
        external_id="beta",
        full_name="synthetic-company/beta",
    )
    collection = _collection(FRONTEND_ID)
    with pytest.raises(
        RepositoryRelationshipValidationError,
        match="one static collection",
    ):
        build_repository_relationship_analysis(
            portfolio=_portfolio(alpha, beta),
            collections=[collection, collection],
        )

    repeated = [
        _signal(
            source_id=FRONTEND_ID,
            relationship_type=RelationshipType.CALLS_API_OF,
            target=f"missing-{index}",
            path=f"src/{index}.py",
        )
        for index in range(3)
    ]
    with pytest.raises(
        RepositoryRelationshipLimitError,
        match="signal",
    ):
        build_repository_relationship_analysis(
            portfolio=_portfolio(alpha, beta),
            signals=repeated,
            policy=RepositoryRelationshipPolicy(
                max_relationships=1,
                max_evidence_refs_per_relationship=2,
            ),
        )
