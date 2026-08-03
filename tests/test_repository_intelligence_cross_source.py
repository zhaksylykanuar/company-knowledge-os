from __future__ import annotations

import copy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.github_normalization_service import (
    build_normalized_issue,
    build_normalized_pull_request,
)
from app.services.repository_intelligence.cross_source import (
    CROSS_SOURCE_METADATA_KEY,
    MAX_CROSS_SOURCE_CLAIM_BYTES,
    RepositoryCrossSourceClaimSetV1,
    _claim_set_from_source,
)


def _claim(
    *,
    repository_id=None,
    repository_full_name: str = "synthetic-company/service",
) -> dict:
    return {
        "schema_version": "repository_cross_source_claim.v1",
        "repository_id": str(repository_id or uuid4()),
        "repository_full_name": repository_full_name,
        "fact_type": "purpose",
        "claim_id": "purpose.primary",
        "field": "repository_type",
        "expected_value": "backend_service",
        "summary": "A strict synthetic source assertion.",
        "confidence": 0.8,
    }


def _claim_set(claims: list[dict]) -> dict:
    return {
        "schema_version": "repository_cross_source_claim_set.v1",
        "claims": claims,
    }


def test_cross_source_claim_set_accepts_one_exact_repository() -> None:
    claim = _claim()
    result = RepositoryCrossSourceClaimSetV1.model_validate(
        _claim_set([claim])
    )
    assert len(result.claims) == 1
    assert result.claims[0].expected_value == "backend_service"


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("unknown_field", True),
        ("repository_full_name", "not-a-full-name"),
        ("claim_id", "Purpose Primary"),
        ("expected_value", "unknown"),
        ("confidence", True),
        ("confidence", "0.8"),
        ("confidence", float("nan")),
        ("confidence", float("inf")),
    ],
)
def test_cross_source_claim_rejects_unsupported_or_unsafe_values(
    mutation: str,
    value,
) -> None:
    claim = _claim()
    claim[mutation] = value
    with pytest.raises(ValidationError):
        RepositoryCrossSourceClaimSetV1.model_validate(
            _claim_set([claim])
        )


def test_cross_source_claim_rejects_invalid_fact_field_pair() -> None:
    claim = _claim()
    claim.update(
        {
            "fact_type": "responsibility",
            "claim_id": "responsibility.orders",
            "field": "repository_type",
            "expected_value": "backend_service",
        }
    )
    with pytest.raises(ValidationError):
        RepositoryCrossSourceClaimSetV1.model_validate(_claim_set([claim]))


def test_cross_source_claim_set_rejects_duplicates_and_mixed_repositories() -> None:
    repository_id = uuid4()
    first = _claim(repository_id=repository_id)
    duplicate = copy.deepcopy(first)
    with pytest.raises(ValidationError):
        RepositoryCrossSourceClaimSetV1.model_validate(
            _claim_set([first, duplicate])
        )

    foreign = _claim(
        repository_id=uuid4(),
        repository_full_name="synthetic-company/other",
    )
    with pytest.raises(ValidationError):
        RepositoryCrossSourceClaimSetV1.model_validate(
            _claim_set([first, foreign])
        )


def test_cross_source_source_parser_bounds_and_rejects_malformed_json() -> None:
    malformed, malformed_code = _claim_set_from_source(
        {
            "source_type": "document",
            "claim_set": "{not-json",
        }
    )
    assert malformed is None
    assert malformed_code == "claim_set_invalid_json"

    oversized, oversized_code = _claim_set_from_source(
        {
            "source_type": "document",
            "claim_set": "x" * (MAX_CROSS_SOURCE_CLAIM_BYTES + 1),
        }
    )
    assert oversized is None
    assert oversized_code == "claim_set_too_large"

    invalid, invalid_code = _claim_set_from_source(
        {
            "source_type": "task",
            "claim_set": {"unexpected": True},
        }
    )
    assert invalid is None
    assert invalid_code == "claim_set_invalid"


@pytest.mark.parametrize(
    "builder",
    [build_normalized_issue, build_normalized_pull_request],
)
def test_github_normalization_preserves_only_sanitized_structured_claims(
    builder,
) -> None:
    claim_set = _claim_set([_claim()])
    result = builder(
        {
            "id": "synthetic-work-item",
            "number": 7,
            "title": "Synthetic structured claim",
            "state": "open",
            "repository_full_name": "synthetic-company/service",
            "source_url": (
                "https://github.com/synthetic-company/service/issues/7"
            ),
            "metadata": {
                CROSS_SOURCE_METADATA_KEY: claim_set,
                "api_token": "must-not-survive",
            },
        }
    )
    assert result["metadata"][CROSS_SOURCE_METADATA_KEY] == claim_set
    assert "api_token" not in result["metadata"]
    assert "must-not-survive" not in repr(result)
