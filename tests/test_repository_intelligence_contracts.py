from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.action_proposal_service import action_evidence_ref_matches_schema
from app.services.repository_intelligence.contracts import (
    HumanResolutionV1,
    RepositoryIntelligenceContractError,
    RepositoryIntelligenceV1,
    validate_repository_intelligence_json,
)
from app.services.repository_intelligence.taxonomy import (
    HumanResolutionStatus,
    REPOSITORY_INTELLIGENCE_MAX_BYTES,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "repository_intelligence"
VALID_FIXTURES = tuple(sorted((FIXTURE_ROOT / "valid").glob("*.json")))
INVALID_FIXTURES = tuple(sorted((FIXTURE_ROOT / "invalid").glob("*.json")))


def _fixture(relative: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _backend_payload() -> dict[str, Any]:
    return _fixture("valid/backend_l1.json")


def _purpose(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["result"]["purpose"]


def _relationship(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["result"]["relationship_candidates"][0]


@pytest.mark.parametrize("fixture_path", VALID_FIXTURES, ids=lambda path: path.stem)
def test_valid_repository_intelligence_fixtures(fixture_path: Path) -> None:
    model = validate_repository_intelligence_json(
        fixture_path.read_bytes()
    )

    assert model.schema_version == "repository_intelligence.v1"
    assert model.result.schema_version == "repository_analyzer_result.v1"


@pytest.mark.parametrize("fixture_path", INVALID_FIXTURES, ids=lambda path: path.stem)
def test_invalid_repository_intelligence_fixtures(fixture_path: Path) -> None:
    with pytest.raises(RepositoryIntelligenceContractError):
        validate_repository_intelligence_json(fixture_path.read_bytes())


def test_contract_rejects_unknown_fields_and_malformed_uuid() -> None:
    unknown = _backend_payload()
    unknown["unexpected"] = True
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(unknown)

    malformed = _backend_payload()
    malformed["workspace_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(malformed)


def test_contract_requires_stable_repository_identity() -> None:
    for missing in ("provider", "external_id", "full_name"):
        payload = _backend_payload()
        payload["repository"].pop(missing)
        with pytest.raises(ValidationError):
            RepositoryIntelligenceV1.model_validate(payload)

    invalid_name = _backend_payload()
    invalid_name["repository"]["full_name"] = "repository-without-owner"
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(invalid_name)


@pytest.mark.parametrize("audit_level", ("L1", "L2"))
def test_l1_and_l2_require_exact_full_sha(audit_level: str) -> None:
    payload = _backend_payload()
    payload["audit_level"] = audit_level
    payload["analysis_target"] = {
        "target_status": "unavailable",
        "commit_algorithm": None,
        "commit_sha": None,
        "metadata_snapshot_id": "synthetic",
    }
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(payload)


@pytest.mark.parametrize(
    "commit_sha",
    (
        "0123456",
        "G" * 40,
        "ABCDEF0123456789ABCDEF0123456789ABCDEF01",
    ),
)
def test_exact_sha_rejects_short_non_hex_and_uppercase(commit_sha: str) -> None:
    payload = _backend_payload()
    payload["analysis_target"]["commit_sha"] = commit_sha
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(payload)


def test_l0_may_model_an_unavailable_sha_without_guessing() -> None:
    model = RepositoryIntelligenceV1.model_validate(
        _fixture("valid/frontend_l0_unavailable.json")
    )

    assert model.analysis_target.commit_sha is None
    assert model.result.purpose.status.value == "insufficient_evidence"
    assert model.result.purpose.evidence_refs == []


def test_evidence_contract_is_object_shaped_and_matches_existing_validator() -> None:
    evidence = _purpose(_backend_payload())["evidence_refs"][0]
    assert action_evidence_ref_matches_schema(evidence) is True

    invalid = _backend_payload()
    _purpose(invalid)["evidence_refs"] = [
        {
            "kind": "repository_file",
            "source": "github",
            "source_record_id": "not-a-uuid",
        }
    ]
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(invalid)


def test_factual_claim_requires_evidence_but_insufficient_evidence_does_not() -> None:
    factual = _backend_payload()
    _purpose(factual)["evidence_refs"] = []
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(factual)

    unknown = _fixture("valid/frontend_l0_unavailable.json")
    assert RepositoryIntelligenceV1.model_validate(unknown)


@pytest.mark.parametrize(
    "confidence",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.01,
        1.01,
    ),
)
def test_confidence_must_be_finite_and_in_range(confidence: float) -> None:
    payload = _backend_payload()
    _purpose(payload)["confidence"] = confidence
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(payload)


@pytest.mark.parametrize("status", ("confirmed", "rejected", "stale", "mystery"))
def test_analyzer_cannot_emit_human_or_reconciliation_status(status: str) -> None:
    payload = _backend_payload()
    _purpose(payload)["status"] = status
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(payload)


def test_human_resolution_requires_actor_and_timezone_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        HumanResolutionV1(
            status=HumanResolutionStatus.CONFIRMED,
        )
    with pytest.raises(ValidationError):
        HumanResolutionV1(
            status=HumanResolutionStatus.CONFIRMED,
            resolved_by_user_id=uuid4(),
            resolved_at=datetime(2026, 7, 30),
        )

    resolution = HumanResolutionV1(
        status=HumanResolutionStatus.CONFIRMED,
        resolved_by_user_id=uuid4(),
        resolved_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    assert resolution.status == HumanResolutionStatus.CONFIRMED


def test_relationship_rejects_self_edge_and_cross_workspace_edge() -> None:
    self_edge = _backend_payload()
    relation = _relationship(self_edge)
    relation["to_repository"] = copy.deepcopy(relation["from_repository"])
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(self_edge)

    cross_workspace = _backend_payload()
    _relationship(cross_workspace)["to_repository"]["workspace_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(cross_workspace)


def test_relationship_rejects_unknown_and_inverse_view_types() -> None:
    for invalid_type in ("unknown", "provides_api_to", "not-a-real-type"):
        payload = _backend_payload()
        _relationship(payload)["relationship_type"] = invalid_type
        with pytest.raises(ValidationError):
            RepositoryIntelligenceV1.model_validate(payload)


def test_relationship_rejects_an_inverse_duplicate() -> None:
    payload = _backend_payload()
    first = _relationship(payload)
    inverse_duplicate = copy.deepcopy(first)
    inverse_duplicate["relationship_id"] = "relationship.inverse-duplicate"
    inverse_duplicate["from_repository"], inverse_duplicate["to_repository"] = (
        inverse_duplicate["to_repository"],
        inverse_duplicate["from_repository"],
    )
    inverse_duplicate["relationship_type"] = "provides_api_to"
    payload["result"]["relationship_candidates"].append(inverse_duplicate)

    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(payload)


def test_symmetric_relationships_normalize_and_deduplicate() -> None:
    payload = _backend_payload()
    first = _relationship(payload)
    first["relationship_type"] = "operationally_coupled_with"
    reversed_duplicate = copy.deepcopy(first)
    reversed_duplicate["relationship_id"] = "relationship.symmetric-duplicate"
    reversed_duplicate["from_repository"], reversed_duplicate["to_repository"] = (
        reversed_duplicate["to_repository"],
        reversed_duplicate["from_repository"],
    )
    payload["result"]["relationship_candidates"].append(reversed_duplicate)

    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(payload)

    payload["result"]["relationship_candidates"] = [reversed_duplicate]
    model = RepositoryIntelligenceV1.model_validate(payload)
    normalized = model.result.relationship_candidates[0]
    assert normalized.from_repository.external_id == "synthetic-backend-101"
    assert normalized.to_repository.external_id == "synthetic-catalog-202"


def test_unresolved_repository_remains_a_candidate() -> None:
    model = RepositoryIntelligenceV1.model_validate(_backend_payload())
    target = model.result.relationship_candidates[0].to_repository

    assert target.resolution_status.value == "candidate"
    assert target.repository_id is None


def test_contradiction_preserves_both_claims_and_evidence() -> None:
    model = RepositoryIntelligenceV1.model_validate(
        _fixture("valid/contradiction_l1.json")
    )
    contradiction = model.result.contradictions[0]
    claims = {claim.claim_id: claim for claim in model.result.claims()}

    assert contradiction.left_claim_id in claims
    assert contradiction.right_claim_id in claims
    assert claims[contradiction.left_claim_id].evidence_refs
    assert claims[contradiction.right_claim_id].evidence_refs


def test_contradiction_rejects_dangling_self_and_duplicate_pairs() -> None:
    dangling = _fixture("valid/contradiction_l1.json")
    dangling["result"]["contradictions"][0]["right_claim_id"] = "missing.claim"
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(dangling)

    self_link = _fixture("valid/contradiction_l1.json")
    contradiction = self_link["result"]["contradictions"][0]
    contradiction["right_claim_id"] = contradiction["left_claim_id"]
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(self_link)

    duplicate = _fixture("valid/contradiction_l1.json")
    second = copy.deepcopy(duplicate["result"]["contradictions"][0])
    second["contradiction_id"] = "contradiction.duplicate"
    second["left_claim_id"], second["right_claim_id"] = (
        second["right_claim_id"],
        second["left_claim_id"],
    )
    duplicate["result"]["contradictions"].append(second)
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(duplicate)


def test_analyzer_cannot_assert_persisted_finding_lifecycle() -> None:
    for lifecycle in (
        "open",
        "resolved",
        "regressed",
        "accepted_risk",
        "false_positive",
    ):
        payload = _backend_payload()
        payload["result"]["findings"][0]["lifecycle_status"] = lifecycle
        with pytest.raises(ValidationError):
            RepositoryIntelligenceV1.model_validate(payload)


def test_item_count_limit_and_top_level_byte_limit_are_enforced() -> None:
    too_many = _backend_payload()
    unknown = too_many["result"]["unknowns"][0]
    too_many["result"]["unknowns"] = [
        {**unknown, "unknown_id": f"unknown.item-{index}"}
        for index in range(51)
    ]
    with pytest.raises(ValidationError):
        RepositoryIntelligenceV1.model_validate(too_many)

    oversized = json.dumps(
        {
            **_backend_payload(),
            "result": {
                **_backend_payload()["result"],
                "limitations": ["x" * 2000 for _ in range(40)],
            },
        }
    )
    assert len(oversized.encode("utf-8")) > REPOSITORY_INTELLIGENCE_MAX_BYTES
    with pytest.raises(RepositoryIntelligenceContractError):
        validate_repository_intelligence_json(oversized)


def test_secret_like_and_unsupported_evidence_fields_are_rejected() -> None:
    for evidence in (
        {
            "kind": "repository_file",
            "source": "github",
            "ref": "synthetic",
            "token": "not-allowed",
        },
        {
            "kind": "repository_file",
            "source": "github",
            "ref": "synthetic",
            "password": "not-allowed",
        },
    ):
        payload = _backend_payload()
        _purpose(payload)["evidence_refs"] = [evidence]
        with pytest.raises(ValidationError):
            RepositoryIntelligenceV1.model_validate(payload)


def test_raw_json_error_is_sanitized_and_does_not_echo_payload() -> None:
    marker = "private-source-marker-that-must-not-appear"
    raw = json.dumps({"schema_version": marker})

    with pytest.raises(RepositoryIntelligenceContractError) as exc_info:
        validate_repository_intelligence_json(raw)

    assert marker not in str(exc_info.value)
