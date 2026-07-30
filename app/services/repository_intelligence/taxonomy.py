"""Closed Repository Intelligence v1 taxonomies and contract bounds."""

from enum import StrEnum


REPOSITORY_INTELLIGENCE_SCHEMA_VERSION = "repository_intelligence.v1"
REPOSITORY_ANALYZER_RESULT_SCHEMA_VERSION = "repository_analyzer_result.v1"
REPOSITORY_INTELLIGENCE_MAX_BYTES = 64 * 1024
REPOSITORY_INTELLIGENCE_MAX_ITEMS = 50
REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS = 50


class AuditLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class RepositoryProvider(StrEnum):
    GITHUB = "github"


class TargetStatus(StrEnum):
    EXACT = "exact"
    UNAVAILABLE = "unavailable"


class CommitAlgorithm(StrEnum):
    SHA1 = "sha1"


class AnalyzerClaimStatus(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class HumanResolutionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ReconciliationStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class FindingLifecycleStatus(StrEnum):
    NEW = "new"
    OPEN = "open"
    RESOLVED = "resolved"
    REGRESSED = "regressed"
    ACCEPTED_RISK = "accepted_risk"
    FALSE_POSITIVE = "false_positive"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RepositoryResolutionStatus(StrEnum):
    CANONICAL = "canonical"
    CANDIDATE = "candidate"


class RepositoryType(StrEnum):
    FRONTEND_APPLICATION = "frontend_application"
    BACKEND_SERVICE = "backend_service"
    WORKER = "worker"
    LIBRARY = "library"
    SDK = "sdk"
    CLI = "cli"
    DATA_PIPELINE = "data_pipeline"
    COLLECTOR = "collector"
    INFRASTRUCTURE = "infrastructure"
    DEPLOYMENT_CONFIGURATION = "deployment_configuration"
    MACHINE_LEARNING = "machine_learning"
    TEST_HARNESS = "test_harness"
    DOCUMENTATION = "documentation"
    WEBSITE = "website"
    PROTOTYPE = "prototype"
    MONOREPO = "monorepo"
    LEGACY_REFERENCE = "legacy_reference"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    CALLS_API_OF = "calls_api_of"
    IMPORTS_PACKAGE_FROM = "imports_package_from"
    CONSUMES_EVENT_FROM = "consumes_event_from"
    DEPLOYED_BY = "deployed_by"
    USES_IMAGE_FROM = "uses_image_from"
    GENERATES_CLIENT_FOR = "generates_client_for"
    TESTS = "tests"
    DOCUMENTS = "documents"
    REPLACES = "replaces"
    FORKED_FROM = "forked_from"
    DUPLICATE_CANDIDATE_OF = "duplicate_candidate_of"
    OPERATIONALLY_COUPLED_WITH = "operationally_coupled_with"
    SHARES_SCHEMA_WITH = "shares_schema_with"
    SHARES_DATABASE_WITH = "shares_database_with"
    OWNS_MIGRATIONS_FOR = "owns_migrations_for"


RELATIONSHIP_INVERSE_VIEW: dict[RelationshipType, str] = {
    RelationshipType.CALLS_API_OF: "provides_api_to",
    RelationshipType.IMPORTS_PACKAGE_FROM: "publishes_package_consumed_by",
    RelationshipType.CONSUMES_EVENT_FROM: "produces_event_for",
    RelationshipType.DEPLOYED_BY: "deploys",
    RelationshipType.USES_IMAGE_FROM: "builds_image_for",
    RelationshipType.GENERATES_CLIENT_FOR: "generated_from_contract_in",
}

SYMMETRIC_RELATIONSHIP_TYPES = frozenset(
    {
        RelationshipType.DUPLICATE_CANDIDATE_OF,
        RelationshipType.OPERATIONALLY_COUPLED_WITH,
        RelationshipType.SHARES_DATABASE_WITH,
        RelationshipType.SHARES_SCHEMA_WITH,
    }
)


class EvidenceKind(StrEnum):
    REPOSITORY_METADATA = "repository_metadata"
    REPOSITORY_FILE = "repository_file"
    REPOSITORY_MANIFEST = "repository_manifest"
    REPOSITORY_SYMBOL = "repository_symbol"
    REPOSITORY_WORKFLOW = "repository_workflow"
    REPOSITORY_DEPENDENCY = "repository_dependency"
    REPOSITORY_DEPLOYMENT = "repository_deployment"
    REPOSITORY_TEST_RESULT = "repository_test_result"
    REPOSITORY_SCANNER_RESULT = "repository_scanner_result"
    GITHUB_PULL_REQUEST = "github_pull_request"
    GITHUB_ISSUE = "github_issue"
    JIRA_ISSUE = "jira_issue"
    DOCUMENT = "document"


class EvidenceSource(StrEnum):
    GITHUB = "github"
    JIRA = "jira"
    GMAIL = "gmail"
    DRIVE = "drive"
    INTERNAL = "internal"


class FindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
