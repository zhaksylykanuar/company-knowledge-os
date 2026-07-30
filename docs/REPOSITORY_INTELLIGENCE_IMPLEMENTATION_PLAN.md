# FounderOS Repository Intelligence — Implementation Handoff

Status: RI-001–RI-003 implemented; RI-004 is the next approval-gated slice
Prepared: 2026-07-30
Target repository: `company-knowledge-os`
Primary outcome: understand what every company repository does, how repositories
relate to one another, what risks exist, and how that evidence connects to the
rest of FounderOS.

Implementation update (2026-07-30): strict `repository_intelligence.v1`,
synthetic L0/L1/L2 fixtures and contract tests are implemented under DEC-115.
Canonical workspace-scoped synthetic L0 is implemented under DEC-116. No
persistence model, migration, provider portfolio read, target execution, UI or
LLM path exists yet. Synthetic-only external exact-SHA checkout is implemented
under DEC-117. Preparation status remains `preparing`.

## 1. Decision Summary

Repository audit must be a native FounderOS capability, not a collection of
manually maintained Markdown reports in a separate repository.

FounderOS should:

1. discover repositories through the connected Git provider;
2. preserve canonical repository identity and the exact audited commit;
3. determine the purpose and responsibilities of every repository;
4. discover and validate relationships between repositories;
5. run bounded audit levels appropriate to each repository;
6. persist structured runs, facts, relationships, findings, and evidence;
7. reconcile new runs with old runs so fixed and regressed findings are visible;
8. connect repository knowledge to pull requests, tasks, documents, people,
   products, incidents, and other company sources;
9. create evidence-backed `ActionProposal` drafts when a human chooses to act;
10. keep Markdown, PDF, and Obsidian outputs as generated exports only.

The audited repositories must not be cloned inside the FounderOS Git working
tree. Temporary checkouts and generated scanner artifacts belong in a separate,
ignored runtime data directory and must be deleted according to an explicit
retention policy.

## 2. Why Repository Intelligence Is More Than a Code Audit

A security or quality scan alone cannot answer the founder's main questions:

- What does this repository actually do?
- Which product, service, or business capability depends on it?
- Is it an application, library, infrastructure definition, data pipeline,
  experiment, test harness, documentation site, or obsolete repository?
- Which APIs, packages, queues, databases, storage buckets, events, images, and
  deployment resources does it provide or consume?
- Which other repositories depend on it?
- Which repository is the system of record for a shared contract?
- Where is functionality duplicated?
- Which repository is critical but has no confirmed owner?
- Which documentation or Jira claims contradict the code?
- What changed between two audits, and was an earlier risk fixed or reintroduced?

Therefore the capability is named **Repository Intelligence**. Audit findings
are one output of that capability, alongside repository purpose, capabilities,
interfaces, dependencies, ownership candidates, product placement, and
cross-source contradictions.

## 3. Desired End State

```text
GitHub / future Git providers
                |
                v
      Canonical Repository Inventory
      - stable provider repository ID
      - owner/name aliases
      - default branch and exact SHA
      - visibility, lifecycle, activity
                |
                v
        Repository Analysis Jobs
      - L0 metadata inventory
      - L1 static deep analysis
      - L2 isolated execution
                |
                v
       repository_intelligence.v1
      - purpose and responsibilities
      - capabilities and interfaces
      - internal/external dependencies
      - deploy/runtime topology clues
      - facts, hypotheses, unknowns
      - audit findings and limitations
                |
                v
   Validation -> Evidence validation -> Persistence
                |
                v
   FounderOS canonical memory and read models
   - repositories
   - audit runs
   - repository facts
   - repository relationships
   - findings and lifecycle
   - evidence refs
                |
                v
  Company / Ask / Briefing / ActionProposal
                |
      +---------+----------+-----------+
      |                    |           |
      v                    v           v
   GitHub PRs          Jira tasks    Docs/Comms
```

## 4. Source-of-Truth and Storage Boundaries

### 4.1 Authoritative data

- PostgreSQL and approved raw storage remain the source of truth.
- Canonical `Repository` rows identify repositories inside a workspace.
- Each persisted audit run must reference an exact commit SHA.
- Structured repository facts and relationships must carry evidence.
- Generated reports are projections and can always be rebuilt.

### 4.2 Runtime checkout location

Use a configurable data directory outside the FounderOS repository.

Codebase note (verify before implementing): `<FOUNDEROS_DATA_DIR>` is a **new**
setting to add; it does not exist yet. The current related setting is
`founderos_local_workspace_path` in `app/core/config.py`, which defaults to
`.local/` *inside* this repository. That default is unsuitable for untrusted
repository checkouts, so Repository Intelligence must introduce a separate
setting whose default resolves to a path **outside** the repository working
tree and is not the existing `.local` workspace.

```text
<FOUNDEROS_DATA_DIR>/
  repository-intelligence/
    worktrees/
      <run-id>/
    artifacts/
      <workspace-id>/
        <repository-id>/
          <run-id>/
    cache/
```

Required rules:

- never clone a target repository under `company-knowledge-os/`;
- never commit a checkout or scanner artifact;
- use a new directory per run;
- verify the resolved provider repository and SHA before analysis;
- delete the checkout after completion or failure;
- retain only sanitized, explicitly allowlisted artifacts;
- set time, disk, memory, process, and output limits;
- do not expose FounderOS credentials or its `.env.local` to analyzed code.

### 4.3 Optional repository-owned configuration

A target repository may contain:

```text
.founderos/audit.yaml
```

Example:

```yaml
schema_version: repository-audit-config.v1
profile: backend_service
criticality: high
roots:
  - app
  - tests
exclude:
  - vendor
  - generated
declared_commands:
  lint: uv run ruff check .
  typecheck: uv run mypy app
  test: uv run pytest
```

This file is advisory configuration, not unquestioned truth. Commands from an
untrusted repository must never run on the FounderOS host merely because they
are declared here. FounderOS centrally controls profiles, allowed tools, limits,
network policy, and whether executable verification is permitted.

## 5. Required Analysis of Every Repository

Every repository profile should explicitly attempt to answer the following
sections. If evidence is insufficient, use `null`, an empty array, or
`insufficient_evidence`; do not invent an answer.

### 5.1 Identity and observed state

- stable provider repository ID;
- current and historical `owner/name`;
- source URL;
- default branch;
- exact audited commit SHA;
- visibility;
- archived, fork, template, or mirror status;
- created, updated, and last-pushed timestamps;
- primary languages and manifests;
- license and repository governance files;
- latest successful source sync and audit freshness.

### 5.2 Purpose

Produce:

- one-sentence purpose;
- longer operational summary;
- repository type;
- lifecycle candidate;
- criticality candidate;
- product or business-area candidates;
- confidence;
- explicit supporting and contradicting evidence;
- unresolved questions requiring human confirmation.

Allowed repository type examples:

```text
frontend_application
backend_service
worker
library
sdk
cli
data_pipeline
collector
infrastructure
deployment_configuration
machine_learning
test_harness
documentation
website
prototype
monorepo
legacy_reference
unknown
```

Purpose evidence may include:

- repository description and topics;
- README and architecture documents;
- manifests and entrypoints;
- API routes and schemas;
- package metadata;
- container and deployment definitions;
- imports and published packages;
- CI workflows;
- directory structure;
- linked issues, pull requests, Jira tasks, and documents.

README text is evidence, but it is not automatically authoritative. Code,
deployment configuration, package metadata, and recent activity may contradict
it. Contradictions must be stored rather than silently resolved.

### 5.3 Responsibilities and capabilities

Identify what the repository owns or implements:

- user-facing surfaces;
- business capabilities;
- background processing;
- data collection and transformation;
- shared libraries or contracts;
- authentication and authorization;
- integrations;
- observability;
- infrastructure and deployment;
- scheduled jobs;
- migrations and data ownership;
- operational tooling.

Each responsibility should include confidence and evidence. Multiple
repositories may participate in one capability, but the system must distinguish:

- `owns`;
- `implements`;
- `supports`;
- `deploys`;
- `tests`;
- `documents`;
- `legacy_replacement_for`;
- `duplicate_candidate_of`.

### 5.4 Interfaces provided

Identify machine-consumable contracts such as:

- HTTP, REST, GraphQL, gRPC, or WebSocket endpoints;
- CLI commands;
- library/package exports;
- container images;
- queues and topics produced;
- event schemas;
- database schemas or migrations owned;
- files or object-storage formats produced;
- webhooks;
- scheduled jobs;
- infrastructure modules;
- environment-variable names, without values.

Do not persist secret values, credential material, raw `.env` contents, or
private request/response bodies.

### 5.5 Dependencies consumed

Identify:

- internal packages;
- external packages;
- services called;
- APIs consumed;
- queues/topics consumed;
- databases and schemas used;
- object storage;
- container images;
- infrastructure modules;
- generated clients and schema imports;
- build-time and runtime dependencies.

The output must distinguish a declared dependency from an observed runtime
relationship and from an inferred hypothesis.

### 5.6 Runtime and deployment role

Attempt to determine:

- deployable units;
- environments;
- Docker images;
- Kubernetes/Helm resources;
- serverless functions;
- scheduled jobs;
- deployment workflows;
- ports and health endpoints;
- databases, queues, and storage used;
- whether the repository is independently deployable;
- whether deployment is controlled by another repository.

### 5.7 Ownership

Collect owner candidates from:

- CODEOWNERS;
- recent maintainers;
- review history;
- package ownership metadata;
- Jira components;
- linked documentation;
- explicit founder confirmation.

Automated evidence produces only candidates. A durable owner relationship
becomes confirmed only through a human resolution flow.

### 5.8 Quality, security, and operability

At minimum inspect:

- tests and likely test layers;
- linting, formatting, and typing;
- CI checks;
- dependency locking and update automation;
- vulnerability signals;
- secret-scanning signals, never secret values;
- license and policy files;
- deployment safety;
- backup and migration clues;
- health/readiness and observability;
- stale or abandoned code;
- oversized or highly coupled areas;
- documentation freshness;
- known limitations and skipped checks.

## 6. Repository Relationship Graph

Understanding how repositories are connected is a first-class deliverable, not
an optional appendix.

### 6.1 Relationship model

Every candidate edge has:

```text
workspace_id
from_repository_id
to_repository_id
relationship_type
direction
status
confidence
first_seen_run_id
last_seen_run_id
evidence_refs
contradicting_evidence_refs
confirmed_by_user_id (nullable)
confirmed_at (nullable)
```

Candidate relationship types:

```text
imports_package_from
publishes_package_consumed_by
calls_api_of
provides_api_to
produces_event_for
consumes_event_from
shares_schema_with
shares_database_with
owns_migrations_for
deploys
deployed_by
builds_image_for
uses_image_from
generates_client_for
generated_from_contract_in
tests
documents
depends_on
replaces
forked_from
duplicate_candidate_of
part_of_same_product
operationally_coupled_with
unknown
```

Keep direction explicit. `A calls_api_of B` is not interchangeable with
`B provides_api_to A`, even if the UI renders them as a paired relationship.

### 6.2 Relationship status

Use:

```text
observed
inferred
confirmed
rejected
stale
```

- `observed`: direct machine-readable evidence exists.
- `inferred`: multiple clues suggest the relationship, but direct proof is
  absent.
- `confirmed`: a human confirmed the candidate.
- `rejected`: a human rejected it or reconciliation disproved it.
- `stale`: it existed in prior exact-SHA analysis but is no longer observed.

### 6.3 Evidence sources for edges

High-confidence examples:

- dependency manifest references another internal package;
- lockfile resolves to an internal repository package;
- Git submodule points to another repository;
- generated client identifies a schema repository and version;
- deployment workflow checks out or triggers another repository;
- Docker/Helm definition consumes an image built by another repository;
- source code calls a configured internal service with matching deployment
  metadata;
- a queue producer and consumer share an exact topic and schema;
- infrastructure repository deploys the target repository artifact.

Medium-confidence examples:

- matching service names and ports;
- README declarations;
- shared database names;
- cross-repository links in issues or documentation;
- synchronized changes across pull requests;
- identical internal schema definitions.

Low-confidence examples:

- naming similarity;
- shared language or framework;
- commits by the same person;
- proximity in the same GitHub organization.

Low-confidence clues must not become confirmed relationships without stronger
evidence.

### 6.4 Graph validation

The system should detect:

- cycles that may be valid but require visibility;
- missing provider or consumer counterparts;
- multiple repositories claiming ownership of the same database migrations;
- shared database coupling;
- duplicated API or event schemas;
- an application depending on archived repositories;
- a critical repository depending on a stale or ownerless repository;
- deployment references to missing repositories;
- a declared relationship contradicted by code;
- orphan repositories with no observed product, runtime, or dependency links.

## 7. Facts, Hypotheses, Confirmations, and Contradictions

Do not flatten all analysis into one list.

### Observed fact

Example:

```text
Repository A imports package `company-auth` at version X.
```

This requires exact-SHA evidence.

### Inferred hypothesis

Example:

```text
Repository A is probably the public API for Product X.
```

Store confidence, supporting evidence, contradicting evidence, and the reason
human confirmation is needed.

### Human-confirmed company context

Example:

```text
Repository A is owned by Team Y and is a production-critical component of
Product X.
```

Persist the confirming user and timestamp.

### Contradiction

Example:

```text
The README says Repository A deploys Service X, but current deployment manifests
deploy Service Y and the latest workflow no longer references X.
```

Keep both claims and their evidence. Do not silently choose one.

## 8. Audit Levels

### L0 — Inventory and metadata

Purpose: cheap coverage of every repository.

Checks:

- identity and activity;
- manifests and languages;
- repository type candidate;
- README, license, tests, CI, CODEOWNERS;
- deploy hints;
- initial purpose and area candidate;
- basic repository relationships from metadata.

Run:

- after every successful repository sync;
- whenever repository metadata or default branch changes.

The existing computed `repo_audit.py` is an L0 compatibility projection. It
should eventually read canonical workspace-scoped repository/source data rather
than remain the durable audit implementation.

### L1 — Static deep analysis

Purpose: understand code structure and contracts without executing repository
code.

Checks:

- entrypoints and architecture boundaries;
- responsibilities and capabilities;
- manifests and dependency graph;
- API/schema/event contracts;
- internal repository edges;
- CI/CD and deployment topology;
- tests, security, documentation, maintainability;
- code/document and cross-source contradictions.

Run:

- when the default-branch SHA changes;
- when the analysis policy or engine version changes;
- on a bounded periodic schedule.

### L2 — Isolated executable verification

Purpose: run approved builds or checks safely.

Examples:

- tests;
- lint;
- type checking;
- build;
- dependency audit;
- repository-specific approved verification.

Required isolation:

- dedicated ephemeral container or stronger sandbox;
- non-root user;
- read-only source where possible;
- no FounderOS socket, filesystem, database, or secrets;
- no GitHub installation token inside the execution environment;
- network disabled by default;
- explicit allowlist if dependency download is required;
- CPU, RAM, disk, process, output, and wall-time limits;
- no privileged mode;
- no host Docker socket;
- sanitized logs and artifacts;
- human approval for the first execution profile of a repository class.

L2 must not be implemented by directly running target repository commands on
the FounderOS host.

## 9. Canonical Contracts

### 9.1 `repository_intelligence.v1`

Illustrative top-level shape:

```json
{
  "schema_version": "repository_intelligence.v1",
  "repository": {
    "provider": "github",
    "external_id": "<stable-provider-id>",
    "full_name": "owner/repo",
    "default_branch": "main"
  },
  "analysis_target": {
    "commit_sha": "<full-sha>",
    "profile": "backend_service",
    "policy_hash": "<sha256>",
    "engine_version": "<version>"
  },
  "purpose": {
    "summary": null,
    "repository_type": "unknown",
    "confidence": 0.0,
    "evidence_refs": [],
    "contradicting_evidence_refs": [],
    "status": "insufficient_evidence"
  },
  "responsibilities": [],
  "interfaces_provided": [],
  "dependencies_consumed": [],
  "relationship_candidates": [],
  "deployment_units": [],
  "ownership_candidates": [],
  "findings": [],
  "unknowns": [],
  "limitations": []
}
```

Requirements:

- strict schema;
- unknown fields rejected;
- bounded item counts and field lengths;
- exact SHA required for L1/L2;
- evidence required for every factual purpose, responsibility, interface,
  relationship, and finding;
- hypotheses clearly labelled;
- unsupported values rejected rather than repaired silently;
- validation before persistence.

### 9.2 Stable run identity

An audit is not uniquely identified by repository and commit alone.

Use an idempotency key derived from:

```text
workspace_id
repository_id
commit_sha
audit_level
profile
policy_hash
engine_version
```

This allows re-analysis of the same commit when rules or tools change without
silently overwriting historical results.

### 9.3 Evidence

Persist evidence using the canonical FounderOS evidence contract. Preferred
selectors:

```json
{
  "kind": "repository_file",
  "source": "github",
  "source_record_id": "<uuid>",
  "ref": "owner/repo@<sha>:path/to/file.py:120",
  "url": null
}
```

Codebase note (verify before implementing): the repository currently has **three
different evidence shapes**, and RI-001/RI-006 must decide how they relate
rather than assume a single unified contract:

1. `evidence_ref.v1` strict JSON, validated by
   `action_evidence_ref_matches_schema` in
   `app/services/action_proposal_service.py`. Allowed keys are only
   `evidence_ref_id`, `id`, `kind`, `record_id`, `ref`, `source`,
   `source_record_id`, `url`. It requires non-empty `kind` and `source` plus at
   least one selector, and any `evidence_ref_id`/`source_record_id`/`record_id`
   value **must parse as a UUID**. The JSON example above follows this shape, so
   `source_record_id` must be a real UUID; the human-readable
   `owner/repo@<sha>:path` locator belongs in `ref`.
2. The canonical `EvidenceRef` **table** (`app/db/canonical_models.py`, §6.8)
   with different columns: `workspace_id`, `source_record_id` (composite FK to
   `source_records`), `entity_id`, `quote`, `field_path`, `source_url`,
   `confidence`. Persisting a table row therefore needs a real `SourceRecord`
   first.
3. The current `repo_audit.py` L0 output and the repo-audit import endpoint
   (`app/api/action_schemas.py`) use plain `list[str]` evidence such as
   `github_discovery_snapshot:<snapshot>:repo:<name>:metadata`. This is legacy
   string evidence, not the `evidence_ref.v1` object shape.

RI evidence should converge on shapes 1 and 2 (object + table backed by a real
`SourceRecord`) and treat shape 3 as compatibility only. See open question 1 in
section 18.

Other useful kinds:

```text
repository_metadata
repository_manifest
repository_symbol
repository_workflow
repository_dependency
repository_deployment
repository_test_result
repository_scanner_result
github_pull_request
github_issue
jira_issue
document
```

Evidence must never include secret values. For a secret finding, evidence
should identify a sanitized file/location and scanner rule while suppressing
the matched value.

## 10. Persistence Model

The exact migration design must be reviewed before implementation. The
recommended logical entities are:

### `RepositoryAnalysisJob`

Operational execution state:

```text
queued
running
completed
partially_completed
failed
cancelled
```

It should follow the existing durable job patterns:

- lease;
- bounded retries;
- progress;
- cancellation;
- safe failure codes;
- no credentials or raw source in the cursor;
- per-repository isolation so one failure does not stop the portfolio.

### `RepositoryAuditRun`

Immutable result header:

```text
workspace_id
repository_id
source_record_id
commit_sha
default_branch
audit_level
profile
policy_hash
engine_version
status
started_at
completed_at
coverage
limitations
artifact_manifest
```

The structured run should also be represented by, or linked to, an internal
`SourceRecord` with a sanitized payload. Do not store an unbounded raw checkout
or scanner dump in PostgreSQL.

### `RepositoryFact`

Versioned evidence-backed claims:

```text
fact_type
value
claim_status
confidence
first_seen_run_id
last_seen_run_id
evidence_refs
contradicting_evidence_refs
confirmed_by_user_id
confirmed_at
```

Examples:

```text
purpose
repository_type
responsibility
interface_provided
dependency_consumed
deployment_unit
criticality
product_candidate
owner_candidate
```

### `RepositoryRelationship`

The directional cross-repository edge described in section 6.

### `RepositoryAuditFinding`

One durable problem, independent of any single run:

```text
workspace_id
repository_id
fingerprint
rule_id
category
severity
confidence
status
title
summary
first_seen_run_id
last_seen_run_id
resolved_at
recommended_next_step
evidence_refs
```

Finding statuses:

```text
new
open
resolved
regressed
accepted_risk
false_positive
insufficient_evidence
```

Finding identity should be semantic and stable enough to survive line movement.
Prefer repository + rule + normalized resource/symbol/dependency identity over
repository + file line alone.

### Why findings must not live only in one JSON blob

Separate durable findings are required for:

- filtering and prioritization;
- first-seen/last-seen history;
- fix and regression detection;
- human decisions;
- links to ActionProposals, GitHub issues, and Jira tasks;
- portfolio-level aggregation;
- briefing and contradiction generation.

## 11. Reconciliation Across Runs

For every successful, sufficiently complete run:

1. match current facts, edges, and findings by stable fingerprint;
2. update `last_seen_run_id`;
3. create new records for new fingerprints;
4. mark absent prior records resolved or stale only if the run had the required
   coverage;
5. never infer resolution from a partial, failed, or cancelled run;
6. mark a reappearing resolved finding as `regressed`;
7. preserve human `accepted_risk`, `false_positive`, confirmed, and rejected
   decisions;
8. record engine/policy changes so disappearance caused by changed rules is not
   misrepresented as a code fix.

This should follow the same fail-closed principle as provider reconciliation:
absence is meaningful only after a complete, trusted observation.

## 12. FounderOS Integration

### 12.1 Repository Portfolio

Show every repository with:

- purpose;
- repository type;
- product/area candidate;
- lifecycle and criticality;
- confirmed owner or unresolved owner candidate;
- latest audited SHA and freshness;
- open findings by severity;
- inbound and outbound repository dependencies;
- blocking unknowns;
- recent changes.

### 12.2 Repository Detail

Sections:

1. What this repository does.
2. Responsibilities and capabilities.
3. Interfaces it provides.
4. Dependencies it consumes.
5. Repository relationship graph.
6. Runtime and deployment role.
7. Owners and contributors.
8. Quality/security/operability findings.
9. Contradictions and unresolved questions.
10. Audit history and evidence.
11. Related PRs, GitHub issues, Jira tasks, documents, and ActionProposals.

### 12.3 Company-wide graph and risk views

FounderOS should be able to surface:

- critical dependency chains;
- shared infrastructure and database coupling;
- ownerless critical repositories;
- archived dependencies still in use;
- duplicated capabilities;
- conflicting contracts or schemas;
- single points of failure;
- stale repositories in active products;
- one vulnerability or dependency issue affecting several repositories;
- Jira work marked done without corresponding code evidence;
- code changes without updated documentation;
- repositories with no observed connection to a current product or capability.

### 12.4 `Спросить`

Target questions:

- «Что делает каждый репозиторий?»
- «Покажи архитектуру наших сервисов и доказательства связей».
- «От чего зависит backend продукта X?»
- «Какие репозитории являются критическими и не имеют владельца?»
- «Где у нас дублируется функциональность?»
- «Что изменилось в архитектуре за последний месяц?»
- «Какие Jira-задачи не подтверждаются изменениями в коде?»

Every answer must distinguish facts, interpretations, unknowns, and
contradictions and must link to evidence.

### 12.5 Briefing

Potential evidence-backed briefing signals:

- new critical or high-severity finding;
- critical relationship appeared or disappeared;
- repository became stale;
- critical repository lost confirmed ownership;
- resolved finding regressed;
- documentation/code contradiction appeared;
- dependency on an archived repository;
- audit coverage is stale or incomplete.

### 12.6 Actions

Workflow:

```text
Finding or unresolved question
  -> user selects proposed follow-up
  -> FounderOS creates ActionProposal
  -> human reviews and approves
  -> GitHub issue or Jira task is created
  -> external receipt is linked
  -> later audit verifies the result
```

`ActionProposal` is the controlled action layer. It is not the source of truth
for audit runs or findings.

The existing repo-audit import endpoint should eventually consume validated
canonical finding IDs/evidence rather than arbitrary external report text.

## 13. Product / Component / Repository Model

Do not equate one repository with one Jira project.

Target conceptual graph:

```text
Company
  -> Product or Business Capability
      -> Component or Service
          -> Repository
              -> Deployable Unit
```

Valid real-world variations:

- one component may span several repositories;
- one monorepo may contain several components;
- one shared library may support multiple products;
- an infrastructure repository may deploy many components;
- a documentation repository may describe several products;
- a test repository may validate another repository;
- a legacy repository may have no active product but still be evidence.

Until durable Product/Component models are implemented:

- keep repository-level facts operational;
- store product/component references as candidates, not facts;
- require human confirmation for durable placement;
- do not block portfolio audit on the future product graph.

## 14. Security and Privacy Boundaries

Mandatory:

- target source is untrusted data;
- repository text cannot override agent or system instructions;
- no direct LLM mutation of production data;
- no repository command execution on the FounderOS host;
- no tokens, API keys, credential values, webhook secrets, `.env` contents, or
  secret matches in results;
- no raw private source bodies in UI, logs, docs, or prompts by default;
- bounded source chunks for any LLM analysis;
- strict JSON validation before persistence;
- evidence validation before persistence;
- network disabled by default for L2;
- sanitized operator errors and logs;
- workspace-scoped reads and writes;
- deletion and retention behavior defined before production rollout;
- no GitHub/Jira write without the existing human approval boundary.

LLM analysis should receive only the minimum source fragments required for the
specific extraction task, with stable source identifiers needed to create
evidence references.

## 15. Scheduling and Cost Control

For 20+ repositories, do not run the most expensive analysis every time.

Recommended policy:

| Level | Trigger | Typical scope |
|---|---|---|
| L0 | successful Git sync or metadata change | all repositories |
| L1 | default-branch SHA, policy, or engine change | changed repositories |
| L1 refresh | bounded periodic schedule | active/critical repositories first |
| L2 | explicit approval or approved schedule | critical repositories |

Additional controls:

- priority by criticality and staleness;
- maximum concurrent jobs;
- per-workspace and per-provider rate limits;
- content-hash cache for unchanged files;
- reuse sanitized scanner artifacts only when SHA/policy/tool versions match;
- skip generated/vendor paths using centrally controlled rules;
- store cost, duration, coverage, and skipped-check receipts;
- stop recursive analysis at explicit depth and repository count limits.

## 16. Implementation Phases

### Hard gate — prepare everything before reading company repositories

The entire preparation track below must be completed without reading, cloning,
or auditing any company repository other than `company-knowledge-os` itself.
Until the **Repository Intelligence Prepared** milestone is explicitly accepted:

- do not open or clone the 20+ target repositories;
- do not call GitHub/Jira or any other provider for repository content;
- do not execute code from a target repository;
- do not derive real repository purpose, ownership, dependencies, or findings;
- do not create real GitHub/Jira follow-up work;
- use only synthetic, repository-owned fixtures containing no company data.

Preparation can make the contracts, persistence, workers, analyzers, isolation,
import, reconciliation, UI/read models, prompts, and runbooks ready. It cannot
truthfully fill in what the real repositories do or how they connect before
they are read. Those facts are produced only by the separately approved
portfolio run after the readiness gate.

### Phase 0 — Discovery and ADR, no migration

Deliverables:

- confirm current GitHub canonical read path;
- inventory existing L0 audit and repo-audit import behavior;
- define `repository_intelligence.v1`;
- define evidence kinds and bounded limits;
- define purpose, fact, edge, and finding taxonomies;
- define isolation threat model and retention;
- write a durable decision in `docs/DECISIONS.md`;
- create three synthetic fixture repositories owned by this test suite:
  - one synthetic frontend;
  - one synthetic backend/service;
  - one synthetic infrastructure, collector, or legacy-shaped repository.

Done when:

- schemas have valid and invalid fixtures;
- unresolved product/data-model decisions are explicit;
- no target repository code has been executed;
- implementation is decomposed into reviewable tickets.

### Phase 1 — Canonical L0 Repository Intelligence

Deliverables:

- run L0 from canonical workspace-scoped repository/source data;
- exact repository identity and latest SHA/freshness;
- purpose/type candidates;
- current metadata risks;
- sanitized evidence refs;
- portfolio and repository-detail read contracts.

During preparation, build and validate Phase 1 against synthetic or seeded
canonical fixtures only. Producing an L0 result for every real connected
repository happens in the approved portfolio run after the prepared milestone,
not during preparation.

Done when:

- the L0 read model produces a valid result for each seeded/synthetic fixture
  repository (real connected repositories are populated only in the portfolio run);
- no filesystem snapshot is treated as workspace-scoped product truth;
- missing evidence returns unknown, not a guessed fact;
- focused tests, `uv run ruff check .`, and guarded `make backend-check` pass
  against an explicit test-marked `FOUNDEROS_TEST_DATABASE_URL`.

### Phase 2 — Static Deep Analyzer Against Synthetic Repositories

Deliverables:

- safe temporary checkout manager;
- static collectors for manifests, entrypoints, interfaces, dependencies,
  deployment, tests, and documentation;
- strict analyzer output;
- purpose and responsibility extraction;
- relationship candidate extraction;
- sanitized artifacts and cleanup.

Done when:

- all three synthetic repository classes produce valid results;
- one repository failure does not stop the other two;
- exact SHA and analyzer versions are visible;
- checkouts are deleted after the run;
- no company repository was read and no fixture repository code was executed.

### Phase 3 — Durable Runs, Facts, Edges, and Findings

This phase changes persistence behavior and requires a branch and PR under the
repository workflow.

Deliverables:

- reviewed migration;
- job/run/fact/relationship/finding persistence;
- internal `SourceRecord` and canonical evidence integration;
- stable fingerprints;
- complete-run reconciliation;
- workspace isolation and RBAC;
- deletion and retention contract.

Done when:

- retries are idempotent;
- partial runs cannot resolve prior findings or edges;
- regressions are detected;
- same-workspace FK and cross-workspace denial tests pass;
- migrations upgrade and downgrade safely;
- `alembic check`, focused tests, `uv run ruff check .`, and guarded
  `make backend-check` pass against an explicit test-marked database.

### Phase 4 — Repository Portfolio, Detail, and Graph UI

Deliverables:

- portfolio page;
- repository detail page;
- directional relationship graph;
- evidence drawer;
- unknown/confirmation queue;
- audit history and freshness;
- filters for product, type, owner, lifecycle, severity, and staleness.

Done when:

- users can answer what each repository does and how it connects;
- observed, inferred, and confirmed relationships are visually distinct;
- raw private source is not exposed;
- desktop/mobile accessibility, overflow, console, typecheck, lint, tests, and
  build checks pass.

### Phase 5 — Cross-source Intelligence

Deliverables:

- link repository facts/findings to PRs and GitHub issues;
- link to Jira tasks and documents;
- detect bounded contradictions;
- add evidence-backed briefing signals and `Спросить` retrieval;
- human confirmation for product/component and owner candidates.

Done when:

- FounderOS can explain a cross-source conclusion with exact evidence;
- existing work is reused instead of blindly creating duplicate tasks;
- contradictions preserve both claims and sources;
- unsupported conclusions are rejected.

### Phase 6 — Isolated L2 Verification

Deliverables:

- approved sandbox/container design;
- profile-specific command allowlists;
- network, resource, output, and artifact controls;
- safe test/build/lint receipts;
- destructive/escape/resource test fixtures;
- synthetic-only executable pilot before any real-repository approval.

Done when:

- target code cannot access FounderOS secrets, database, sockets, or host Docker;
- timeout and resource exhaustion are contained;
- results are sanitized;
- a failed executable audit cannot damage FounderOS or block other repositories;
- no company repository code has been executed.

### Phase 7 — Controlled Follow-up

Deliverables:

- finding-to-ActionProposal workflow;
- deduplication against existing GitHub/Jira work;
- external receipt linkage;
- audit verification of the eventual fix;
- accepted-risk and false-positive decisions.

Done when:

- no external action occurs without explicit human approval;
- every proposal has validated evidence;
- synthetic end-to-end fixtures prove that a later complete audit can mark a
  finding fixed or regressed;
- no real external task was created.

### Repository Intelligence Prepared milestone

This milestone is the end of preparation and the only point after which the
founder may launch agents in company repositories.

Required evidence:

- the implementation plan and durable decisions are committed;
- `repository_intelligence.v1` and all enums/limits are versioned and frozen
  for the first portfolio run;
- synthetic L0/L1 fixtures pass for frontend, backend, and infrastructure
  repository classes;
- job, run, fact, relationship, finding, evidence, and reconciliation paths
  pass against the dedicated test database;
- temporary checkout and artifact cleanup are proven without company source;
- L2 isolation is proven with hostile synthetic fixtures, or L2 is explicitly
  disabled for the first portfolio run;
- one repository failure cannot stop or corrupt other jobs;
- dry-run import and full synthetic import both produce deterministic results;
- repository outputs can be aggregated into a directional cross-repository
  graph;
- no unsupported claim can be persisted;
- no external write can occur without the existing human approval boundary;
- documentation includes the per-repository prompt, central output layout,
  portfolio manifest format, restart/retry procedure, and deletion/retention
  behavior;
- focused tests, `uv run ruff check .`, guarded `make backend-check`,
  migration checks, and secret scans are green;
- a sanitized readiness receipt states that zero company repositories were
  read or executed during preparation.

If any item is missing, status remains `preparing`; do not start the portfolio
run.

### First real portfolio run — separate founder-approved stage

Only after the prepared milestone and an explicit founder instruction:

1. Create an approved portfolio manifest containing stable repository identity
   and the local/provider location for every target repository.
2. Launch the same read-only L0/L1 contract in each repository. Do not edit the
   target working tree and do not commit generated reports there.
3. Write each result to the central audit workspace:

   ```text
   <audit-workspace>/
     runs/
       <repository-id>/
         <commit-sha-or-metadata-snapshot>/
           repository_intelligence.v1.json
           report.md
   ```

4. Import only schema-valid and evidence-valid results into FounderOS.
5. After all repository runs finish, perform a portfolio reconciliation pass
   that resolves directional edges and reports unresolved targets,
   contradictions, duplicate capabilities, and orphan repositories.
6. Ask for human confirmation of owners, products/components, inferred edges,
   and accepted risks.
7. Keep L2 disabled unless the founder separately approves executable
   verification for a bounded repository/profile.

Per-repository agents can propose relationship candidates, but the complete
connection map is finalized only after the central pass has results from all
approved repositories.

## 17. Initial Ticket Breakdown

Keep task prompts short and refer to `AGENTS.md`.

### RI-001 — Contract and fixtures

Status: implemented and verified on synthetic fixtures (DEC-115).

```text
Goal: Define strict repository_intelligence.v1 and fixtures.
Context: docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md.
Constraints: No persistence or provider writes; bounded schema; evidence required.
Done when: Valid/invalid contract tests pass; ruff and guarded backend-check green.
```

#### RI-001 binding requirements and edge cases

These are the implemented RI-001 acceptance criteria. They remain binding for
later Repository Intelligence slices.

1. **Workspace scope is in the contract, not only in persistence.** Every
   top-level payload carries `workspace_id`, and every fact, relationship, and
   finding is workspace-scoped. Reason: workspace isolation is an immutable
   FounderOS invariant, and RI-006 persistence will map to composite
   `(workspace_id, id)` keys that already exist on `source_records`,
   `repositories`, and `evidence_refs`.
2. **Repository identity is stable, not `owner/repo` alone.** Require
   `repository.provider`, `repository.external_id`, and `repository.full_name`.
   Reason: canonical `Repository` is keyed by `(workspace_id, external_id)` and
   `(workspace_id, provider, full_name)`; owner/name can change and must not be
   the sole identity.
3. **`commit_sha` is level-dependent, and cannot be mandatory for L0 today.**
   The canonical `Repository` model stores `default_branch` but **no commit
   SHA**, and current GitHub sync does not persist one. Therefore:
   - L0: `commit_sha` may be `null`; the contract must carry an explicit
     `target_status: exact | unavailable` plus `commit_algorithm` (e.g. `sha1`).
   - L1/L2: a full commit SHA is required (`target_status: exact`).
   Reason: requiring a SHA for L0 would silently depend on RI-002/GitHub
   ingestion work that does not exist yet, so the contract must model
   `unavailable` as a valid state rather than fail closed on every L0 run.
4. **Evidence is object-shaped `evidence_ref.v1`, not `list[str]`.** Each
   evidence item must pass the existing `action_evidence_ref_matches_schema`
   rules in `app/services/action_proposal_service.py`: allowed keys only,
   non-empty `kind` and `source`, at least one selector, and any
   `evidence_ref_id` / `source_record_id` / `record_id` value must parse as a
   UUID. Do not promote the legacy `repo_audit.py` `list[str]` strings to a new
   canonical shape. Reason: a fourth evidence format would fragment the
   evidence contract.
5. **Absent evidence is a valid fail-closed state, not always an error.** A
   factual `observed` / `confirmed` fact, relationship, or finding with empty
   `evidence_refs` is rejected; a `unknown` / `insufficient_evidence` item with
   empty `evidence_refs` is accepted. Reason: the contract must be able to
   express "no evidence" without inventing one.
6. **`confidence` must be a finite float in `[0.0, 1.0]`.** Reject `NaN`,
   `Infinity`, negatives, and values above 1.0. Reason: no existing strict
   validator guards float finiteness, so RI-001 must add this explicitly or
   invalid confidences will pass JSON validation.
7. **Two status vocabularies are separate, and analyzer output is limited.**
   - Claim/relationship status: `observed`, `inferred`, `confirmed`,
     `rejected`, `stale`.
   - Finding lifecycle: `new`, `open`, `resolved`, `regressed`,
     `accepted_risk`, `false_positive`, `insufficient_evidence`.
   Machine analyzer output may only emit `observed` / `inferred` (plus
   `unknown` / `insufficient_evidence`). `confirmed` and `rejected` require
   human provenance (`resolved_by_user_id` + `resolved_at`), mirroring the
   `confirmed_by_user_id` / `confirmed_at` precedent in
   `app/db/company_world_models.py`; `stale` may only originate from
   reconciliation against a prior complete trusted run, never a single RI-001
   payload. Reason: an LLM/analyzer must not self-assert a human decision.
8. **Relationship validation is strict.** Use `from_repository` and
   `to_repository`; reject self-edges (`from == to`), reject cross-workspace
   edges, and reject unknown `relationship_type`. Define directed types with
   their inverse (for example `calls_api_of` <-> `provides_api_to`,
   `deploys` <-> `deployed_by`, `produces_event_for` <-> `consumes_event_from`)
   and normalize symmetric types (for example `operationally_coupled_with`).
   Reason: a free-form `direction` plus a directional type can encode
   contradictory edges.
9. **Contradictions are preserved, not deleted.** Two evidence-backed claims
   that conflict must both persist with a contradiction link; only unsupported
   or structurally impossible claims are rejected. Reason: FounderOS records
   competing evidence rather than silently choosing one.
10. **Bounded and closed.** Use `extra="forbid"`, bounded item counts and
    field lengths, and a top-level byte cap consistent with the existing
    64 KiB / 50-item action-evidence precedent.
11. **`docs/DECISIONS.md` is required, not optional.** RI-001 fixes durable
    decisions (contract shape, workspace scope, evidence convergence,
    human-only statuses, SHA policy, relationship direction, fail-closed
    semantics), so a decision entry is mandatory per `AGENTS.md`.

Required contract tests: valid payload; missing `workspace_id`; malformed UUID;
cross-workspace relationship; self-edge; repository ref without stable identity;
factual item with no evidence (reject) vs `insufficient_evidence` with no
evidence (accept); non-finite / out-of-range `confidence`; unknown status;
analyzer output using a human-only status (reject); unknown / inverse-mismatched
relationship type; and a preserved contradiction (both claims retained).

Sequencing note: RI-002 followed RI-001 and is now complete. Durable storage
and migrations remain **RI-006**, not part of the L0 projection.

### RI-002 — Canonical L0 projection

Status: implemented and verified on synthetic canonical rows (DEC-116).

```text
Goal: Replace filesystem-first product audit reads with workspace-scoped canonical L0.
Context: Existing Repository/SourceRecord GitHub spine and RI plan.
Constraints: Read-only; preserve evidence and unknown states; no provider call.
Done when: Focused tests, ruff, and guarded backend-check green.
```

### RI-003 — Safe checkout manager

Status: implemented and verified on synthetic local repositories (DEC-117).

```text
Goal: Materialize an exact repository SHA in an isolated temporary directory.
Context: RI plan Phase 2.
Constraints: No target execution; no secrets; bounded disk/time; cleanup on all exits.
Done when: Path, SHA, cleanup, timeout, and failure tests pass.
```

### RI-004 — Static collectors

```text
Goal: Extract manifests, entrypoints, interfaces, dependencies, deploy clues, and tests.
Context: Three synthetic fixture repositories (frontend/backend/infra) and RI schema.
Constraints: Static-only; no company repository read; bounded files/bytes; sanitize output; evidence on every fact.
Done when: Synthetic fixtures produce validated deterministic output and checks pass.
```

### RI-005 — Relationship candidates

```text
Goal: Build directional evidence-backed repository relationship candidates.
Context: RI plan section 6.
Constraints: Distinguish observed/inferred; no name-only confirmation; no DB migration.
Done when: Package/API/event/deploy edge fixtures and contradiction tests pass.
```

### RI-006 — Persistence ADR and migration

```text
Goal: Persist runs, facts, relationships, and finding lifecycle.
Context: RI plan sections 9-11 and existing canonical models.
Constraints: Branch/PR required; same-workspace FKs; idempotent reconciliation.
Done when: Migration, isolation, retry, partial-run, regression, and gate checks pass.
```

### RI-007 — Portfolio and detail UI

```text
Goal: Show repository purpose, relationships, findings, unknowns, and evidence.
Context: RI read APIs and product shell.
Constraints: Progressive disclosure; no raw source bodies; observed/inferred distinct.
Done when: UI tests, typecheck, lint, build, browser/accessibility checks pass.
```

### RI-008 — Cross-source contradictions

```text
Goal: Compare repository intelligence with GitHub work, Jira, and documents.
Context: Canonical evidence-backed company memory.
Constraints: Preserve competing claims; strict evidence; no autonomous writes.
Done when: Bounded contradiction fixtures and unsupported-claim rejection pass.
```

### RI-009 — L2 isolation

```text
Goal: Run approved repository checks in a disposable isolated environment.
Context: RI plan security boundary.
Constraints: No host execution, secrets, DB, Docker socket, or default network.
Done when: Escape/resource/timeout/sanitization tests pass on hostile synthetic fixtures; no company repository code is executed; real-repository L2 stays disabled until separately approved.
```

## 18. Questions Requiring Explicit Decisions Before Persistence Work

1. Should audit result payloads use one internal `SourceRecord` per run or a
   small manifest record plus artifacts in raw storage?
2. Which artifact backend is approved for sanitized static-analysis outputs?
3. What exact retention applies to checkouts, scanner artifacts, run metadata,
   facts, evidence, and resolved findings?
4. Which facts require human confirmation before they influence criticality or
   product-level recommendations?
5. Should Product/Component be implemented before Phase 5, or should confirmed
   tags/relations bridge the gap?
6. Which L1 analyzers are allowed to inspect private source, and what maximum
   file/byte/chunk budgets apply?
7. Which L2 dependency-download destinations, if any, may be network-allowlisted?
8. What constitutes complete coverage for each audit profile so reconciliation
   is allowed?

Do not hide these decisions inside implementation code.

## 19. Explicit Non-goals for the First Slice

- auditing all 20+ repositories with L2 immediately;
- executing arbitrary commands from repository documentation;
- treating an LLM summary as a confirmed company fact;
- automatically assigning owners;
- automatically creating GitHub/Jira work;
- building a generic graph database;
- replacing PostgreSQL with a vector store;
- storing full source trees in PostgreSQL;
- exposing private code in generated documentation;
- treating every repository as a separate Jira project;
- implementing a large refactor of existing GitHub or Company Brain code.

## 20. Instructions for the Next Agent

Use this file as planning context, not permission to implement the entire system
in one task.

Before changes:

1. Read `AGENTS.md`, `CLAUDE.md`, `docs/README.md`, this file, and the relevant
   current decision entries.
2. Run `git status --short` and preserve unrelated work.
3. Inspect targeted current implementation files only.
4. Compare this proposal with current code because the repository may have
   changed since 2026-07-30.
5. Restate the selected ticket, relevant files, assumptions, and short plan.
6. Wait for human approval before non-trivial implementation.

Recommended next task: **RI-004 — static collectors**. Inspect only bounded
synthetic checkout contents for manifests, entrypoints, interfaces,
dependencies, deployment clues, tests and documentation. Do not execute target
code.

Do not start with the UI, database migration, an LLM prompt, or executable
repository commands.

## 21. Compact Handoff Prompt

```text
Goal: Implement RI-004 for FounderOS Repository Intelligence.
Context: Read AGENTS.md, CLAUDE.md, docs/README.md, and
docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md. FounderOS must understand
what every repository does and the evidence-backed directional relationships
between repositories.
Constraints: Static-only collectors over synthetic RI-003 checkouts; bounded
files/bytes/depth/output; sanitized evidence for every fact; no target command
execution, company repository read, provider call, migration, UI or LLM
mutation. Preserve unrelated working-tree changes.
Done when: synthetic frontend/backend/infrastructure fixtures produce
deterministic schema-valid collector output, pathological paths stay bounded,
and uv run ruff check . plus guarded make backend-check are green.
```
