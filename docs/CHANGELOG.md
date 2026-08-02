# FounderOS Changelog

## 2026-08-02

### Security

- Pinned GitHub App manifest conversion and installation verification requests
  to a fixed `https://api.github.com` client origin, with validated path
  segments instead of constructing absolute request URLs from callback input.
- Replaced unkeyed GitHub App setup-state hashes with domain-separated HMAC
  digests derived from the existing fail-closed server encryption-key boundary.
  Database state remains a 64-character one-time verifier and cannot be
  recomputed without server key material.
- Reduced local-workspace bootstrap CLI output to a status-only receipt so
  filesystem paths and environment-derived values never reach terminal logs.
- Replaced Jira hostname substring error classification with exact backend
  error contracts and removed a URL-shaped unanchored regular expression from
  the GitHub App frontend tests.

## 2026-07-31

### Added

- Added RI-004 bounded static collectors (DEC-118) over read-only synthetic
  RI-003 exact-SHA checkouts. The deterministic validated result covers
  manifests, entrypoints, package dependencies, HTTP/schema interfaces,
  deployment definitions, tests/CI, documentation and migration/data-object
  clues.
- Added evidence-backed projection into the existing RI-001 claim contract,
  strict output/resource bounds, checkout-manifest verification, sanitized
  errors and stable JSON serialization without retaining source bodies or
  configuration values.
- Added synthetic frontend, backend, infrastructure and pathological collector
  tests proving deterministic output, bounded files/items, evidence on every
  fact, cleanup and zero target-code execution. No persistence, migration, UI,
  provider/company repository read, network operation or LLM path was added.
- Added RI-005 directional relationship candidates and bounded portfolio graph
  validation (DEC-119) over strict synthetic RI-004 facts and a trusted
  workspace-scoped portfolio manifest.
- Added observed/inferred edge status, evidence merging, unresolved candidate
  targets, deterministic symmetric normalization, inverse views, cycle/orphan
  findings, selector ambiguity rejection and fail-closed opposing-direction
  contradiction review. Repository-name similarity alone creates no edge.
- Added synthetic package/API/event/deploy, unresolved, symmetric, cycle,
  orphan, contradiction, workspace/isolation and pathological bound tests. No
  migration, persistence, UI, provider/company repository read, target
  execution or LLM path was added.

## 2026-07-30

### Added

- Added RI-001 strict `repository_intelligence.v1` contracts (DEC-115), with a
  FounderOS-owned workspace/repository envelope, level-dependent SHA rules,
  object-shaped evidence, finite confidence, human-only resolution provenance,
  directional relationship validation and preserved contradiction links.
- Added synthetic frontend L0, backend L1, infrastructure L2 and contradiction
  fixtures plus invalid contract fixtures and focused tests. This slice adds no
  persistence, migration, UI, provider/LLM call, repository checkout or company
  repository read/execution.
- Added RI-002 canonical L0 projection (DEC-116): exact workspace-scoped
  Repository/active SourceRecord joins, SourceRecord-backed evidence, explicit
  unavailable-SHA and unknown states, bounded repository-type candidates and
  the first evidence-backed archived-repository finding.
- Added synthetic database tests for frontend/backend/infrastructure L0,
  cross-workspace isolation, missing/tombstoned/mismatched evidence, unsafe URL
  removal, deterministic output and zero database mutation. No filesystem
  discovery, provider call, checkout, migration, UI or LLM path was added.
- Added RI-003 exact-SHA checkout management (DEC-117) with an external
  `founderos-ri-data` runtime boundary, minimal credential-free git
  environment, protocol denial, bounded tree/blob output and read-only
  materialization.
- Added synthetic checkout tests for historical SHA selection, path and git
  metadata boundaries, symlink/gitlink/alternates rejection, file/disk/path
  limits, sanitized timeout/failure output, no hook or target execution and
  cleanup on success, exception and cancellation.

### Changed

- Added a proposal/handoff for future Repository Intelligence: determining what
  each repository does, mapping directional evidence-backed relationships
  between repositories, staged L0/L1/L2 analysis, durable fact/finding
  reconciliation, FounderOS integration, and an agent-ready ticket sequence.
- Added a complete Russian Repository Intelligence operational guide covering
  worktree/runtime directory layout, reusable FounderOS contracts, RI-001–RI-009
  preparation on synthetic fixtures, the zero-company-data readiness gate, and
  the separately approved 20+ repository portfolio run.
- Made workspace Settings the only credential source for OpenAI, GitHub, Jira,
  Gmail and Google Drive (DEC-114). Provider credentials no longer have
  environment fallbacks.
- Reduced local dotenv loading to the single untracked root `.env.local`;
  `.env.example` now documents bootstrap/deployment controls only.
- GitHub App token minting now requires the encrypted workspace-managed
  credential. Removed the environment GitHub App path, manual installation-row
  endpoint and obsolete offline env-presence preflight.
- Removed the password-through-env admin provisioning script and the legacy
  local organization repository promotion script. Founder creation remains
  invite-only and GitHub setup remains product-managed.
- Replaced GitHub status `missing_env` details with a product-level setup
  requirement and removed deployment variable names from the interface.
- Added the secrets/environment source-of-truth document covering UI-managed
  provider credentials, bootstrap-only runtime settings and current OAuth/KMS
  gaps.

## 2026-07-29

### Added

- Added Memory Control v1 at `/settings/memory` (DEC-113): an exact content-free
  preview, owner/admin correction with prior-version purge, and complete active
  deletion of a FounderOS-authored document plus all versions.
- Added optimistic `updated_at` + version-count concurrency checks, document
  row locks, strict confirmation codes, cross-workspace/RBAC denial and
  private/no-store responses for destructive memory operations.
- Added explicit product boundaries for backup rotation and external provider
  data; FounderOS does not claim that a local active-row deletion immediately
  erases PostgreSQL dead tuples, WAL, backups or the provider source.
- Added workspace AI/privacy controls at `/settings/ai` (DEC-112): encrypted
  OpenAI key lifecycle, allowlisted model/reasoning/budget settings, explicit
  current-policy acknowledgement, enable/disable, read-only safe status and
  two-step credential removal.
- Added a strict connection check that sends one synthetic non-company fact,
  performs provider I/O outside the SQL session, persists only a safe receipt
  and rejects a stale result if configuration changes during the call.
- Added database and API constraints for one workspace-owned AI configuration;
  viewers remain read-only, cross-workspace access fails closed and a workspace
  row never silently falls back to an environment credential.
- Added the optional `assistant.v2` generative second-opinion path (DEC-111):
  bounded exact-snapshot retrieval, strict Responses JSON schema, explicit
  fact/interpretation/objection/recommendation sections, local evidence critic,
  non-persistent provider requests and deterministic fallback.
- Added an independent provider-data-policy acknowledgement gate. An LLM key
  and feature flag alone cannot send company facts outside FounderOS.
- Added a minimal structured second-opinion UI with visible evidence-validation,
  snapshot and no-action boundaries.
- Added maintainability ratchets and a deterministic Headquarters query-budget
  test that rejects SourceRecord-driven N+1 growth (DEC-110).
- Added a dedicated action API schema module, reducing the action route module
  while preserving the exact validated HTTP contracts.
- Added encrypted off-device disaster recovery controls (DEC-108): exact local
  bundle validation, AES-256-GCM export, decrypt-after-write verification,
  isolated full restore drills, safe materialization and explicit 7/4/12
  retention with dry-run by default.
- Added the disaster-recovery runbook with a 24-hour RPO, four-hour RTO, daily
  export and weekly drill contract. The first real independent copy and drill
  remain an owner-operated external gate.
- Added private-source licensing, private vulnerability reporting,
  contribution rules, owner CODEOWNERS and a repository-owned pre-commit
  quality/secret hook (DEC-109).
- Added Durable GitHub Provider Jobs (DEC-107): the API now enqueues a
  PostgreSQL-backed job and returns `202`, while bounded workers claim with
  leases, resume repository progress after crashes, retry transient reads and
  expose cancellation without persisting installation tokens or raw provider
  payloads.
- Added automatic GitHub sync polling and progress receipts to the product UI.
  Owner/admin users can cancel a queued or running read; duplicate launch
  controls remain locked until the job reaches a terminal state.
- Added a current-state Python vulnerability gate with `pip-audit` to the
  guarded backend checker and CI; frontend CI now audits development as well as
  runtime dependencies (DEC-106).
- Added immutable PostgreSQL and Redis manifest digests to local Compose and
  Renovate `docker-compose` tracking so tag and digest updates arrive together.
- Added database-backed `/health/ready`, operator-only low-cardinality runtime
  counters, structured JSON request events and server-generated correlation
  IDs (DEC-104).
- Added explicit browser Origin/Referer enforcement for cookie mutations,
  backend and Next.js security headers, production HSTS, and local-only
  Swagger/ReDoc/OpenAPI.
- Added one shared pre-Argon2 admission boundary for login, founder enrollment
  and teammate password setup. It supports an atomic Redis backend for workers,
  fail-closed Redis errors and trusted-proxy client address resolution
  (DEC-105).
- Added bounded background cleanup for expired sessions, account setup token
  hashes and founder invite hashes.
- Added separate public-liveness, authenticated-session, authenticated-workspace
  and Playwright desktop/mobile browser smoke gates. Playwright stores no
  screenshots, video or traces containing company UI.
- Added enforceable Python static typing to the guarded backend checker and CI.
  The configured `mypy app` gate now passes all 98 application source files.
- Added pinned Biome frontend linting for Next/React correctness,
  accessibility and security across application, component, library and test
  sources.
- Added Database Workspace Isolation v1 (DEC-102): composite workspace foreign
  keys for canonical evidence, pull-request repository/source lineage, task
  source lineage and document versions, with fail-closed migration preflight.
- Added negative database tests proving every covered cross-workspace
  relationship fails at commit.
- Added Strict Action Evidence v1 (DEC-101): a bounded `evidence_ref.v1`
  JSON shape, canonical same-workspace resolution, active-record and exact
  GitHub target checks at approval and execution, plus a second validation
  immediately before provider I/O.
- Added acceptance coverage proving fabricated, deleted, unrelated and
  cross-workspace evidence cannot approve a proposal, and evidence invalidated
  after a durable execution claim still prevents the provider call.
- Added exact Headquarters snapshot enforcement for AI/system approval.
- Added Atomic External Execution v1 (DEC-100): a committed execution claim,
  proposal row lock, workspace-scoped client idempotency, request hash, actual
  requesting user, explicit claim/running/uncertain states and database
  uniqueness for one active or successful execution per proposal.
- Added GitHub uncertain-outcome reconciliation through an exact hidden
  execution marker, a provider-consistency grace period and a read-only proof
  of either a matching issue or a safe new-key retry boundary.
- Added concurrent execution acceptance coverage proving two simultaneous
  requests make one provider call and persist one execution.
- Added a universal pytest database guard that runs before the application
  engine import. It requires explicit test mode and a dedicated test-marked
  PostgreSQL target, compares it with product dotenv/ambient endpoints, and
  disables LLM, connector and external-write capabilities.
- Added CI migration metadata drift detection with `uv run alembic check`.

### Changed

- Removed the legacy direct internal-document DELETE route. Document forgetting
  now uses the exact preview-bound POST contract and is limited to workspace
  owners/admins; ordinary member edits still preserve append-only versions.
- Removed the superseded selected-issue and selected-pull-request synchronous
  GitHub endpoints and services. The unified `202` durable GitHub App job is
  now the only live repository-read route; historical normalized records stay
  readable.
- Removed the legacy synchronous GitHub App sync path that could perform
  sequential provider reads while its caller held a database session. Provider
  I/O now runs outside SQL transactions and each repository is normalized in a
  separate short transaction through a shared HTTP connection pool.
- Declared directly imported `cryptography`, `starlette` and `python-dotenv`,
  raised vulnerable `pydantic-settings`/Starlette floors to fixed releases,
  and regenerated the Python lockfile with no known dependency vulnerabilities.
- Removed unused OpenAI and Google API/OAuth SDKs, Tenacity, obsolete
  Google/email/triage/Jira/Telegram settings, legacy provider placeholders and
  the superseded Codex operator launcher. The later evidence-validated AI path
  uses the existing audited HTTP client and does not reintroduce an SDK.
- Session validation now writes `last_seen_at` only after a configured minimum
  interval instead of on every authenticated request.
- Non-local startup now rejects `SameSite=None`; the product keeps its
  first-party Lax/Strict cookie boundary.
- Active README and local-runtime guidance now use the actual
  «Сейчас / Компания / Спросить / Настройки» navigation and no longer count the
  superseded five-zone browser run as current acceptance.
- Replaced the frontend's fake lint alias to TypeScript typecheck with a
  separate zero-warning Biome gate (DEC-103). React hook dependencies, dialog
  accessibility, unstable list keys and unsafe control-character parsing found
  by the first real run were corrected.
- Tightened backend type boundaries for authentication, ASGI middleware,
  provider services, canonical projections and optional database results
  without weakening runtime validation.
- Scoped GitHub operational SourceRecord joins and repository hydration by
  workspace in addition to the new PostgreSQL constraints.
- Routed bulk approve/reject through the same role-rechecked, row-locked,
  proposal-versioned and client-idempotent decision service as individual
  decisions. Every successful item now returns its own durable receipt.
- Repo-audit import no longer persists arbitrary external evidence strings;
  it stores a canonical repository selector that must resolve in the current
  workspace before approval.
- External provider exceptions no longer become false definitive failures.
  FounderOS keeps the approved proposal blocked behind an `uncertain` receipt
  until read-back reconciliation resolves the outcome.
- Action execution, reconciliation, preview and blocked-execution audit events
  now record the authenticated user instead of a generic operator label.
- Renamed the CI PostgreSQL database from `ckdos` to `ckdos_test` and made the
  test target explicit through `FOUNDEROS_TEST_DATABASE_URL`.
- Replaced active bare-pytest guidance with the guarded `make backend-check`
  workflow (DEC-099).

## 2026-07-27

### Added

- Added GitHub Source Reconciliation v1 (DEC-098). Successful, fully paginated
  server-attested repository reads can tombstone issues and pull requests
  absent from a complete all-state snapshot. Partial, filtered, failed,
  truncated and manual local imports cannot infer deletion.
- Added reversible SourceRecord tombstone provenance: provider snapshot time,
  persistence time, SyncJob and controlled reason. Pull requests now retain
  their canonical SourceRecord link, and disappearance/restoration append
  content-free lifecycle memory events.
- Added Lifecycle Event Ledger v1 (DEC-097): append-only
  `company_memory_events` with a transactional per-workspace sequence,
  controlled lifecycle types, canonical UUID evidence identifiers,
  event/observation time, fingerprint, confidence, access, sensitivity and
  retention. The ledger duplicates no proposal text, source body, provider
  payload or rendered UI copy.
- Added same-transaction, idempotent lifecycle producers for Action Proposal
  creation/approval/rejection and Company World confirmation/dismissal.
- Added the membership-scoped temporal checkpoint foundation (DEC-096),
  storing only the exact source snapshot, observation time and bounded opaque
  signal fingerprints. Membership removal deletes the checkpoint; source text,
  evidence bodies, chats and provider payloads are not duplicated.
- Added snapshot-bound
  `POST /api/v1/workspaces/{workspace_id}/headquarters/changes/checkpoint`.
  Stale acknowledgements fail with `409`; the response is private/no-store and
  reports membership-scoped retention.

### Changed

- Current GitHub operational and Company Brain reads now exclude derived
  Task/PullRequest projections whose SourceRecord is tombstoned. A newer
  trusted provider read restores the object; stale snapshots and untrusted
  manual normalization cannot. PostgreSQL history/evidence is retained and no
  LLM or external write participates.
- Upgraded the checkpoint contract to `temporal-checkpoint.v2` and the
  Headquarters comparison to `temporal-memory.v2`. A checkpoint now combines
  current-signal fingerprints with `last_event_sequence`; supported terminal
  events render as resolved and disappear after the next acknowledgement.
- Upgraded Headquarters to `headquarters.v3`. Temporal signals now separate
  `event_time` from `observed_at`, require evidence, expose confidence, access
  scope and source-bound retention, and distinguish current facts from changes
  after a real checkpoint.
- Reworked the home signal panel into two honest modes: current confirmed facts
  before the first checkpoint and new/changed facts after it. The explicit
  acknowledgement control stores only the technical comparison point and
  refreshes the exact company snapshot.

## 2026-07-25

### Changed

- Replaced the 5,000-line legacy MVP playbook with the FounderOS 2.0 product
  contract (DEC-095): an AI partner with evidence-backed temporal company
  memory, progressive drill-down and human-approved actions.
- Replaced the Living Command Center acceptance ledger with one AI-first
  acceptance ledger and reduced Roadmap/TODO to the active reset and the next
  memory/reasoning phases.
- Defined `Сейчас / Компания / Спросить / Настройки` as the only target product
  zones. Provider-first navigation, synthetic command-center UX and duplicate
  surfaces are superseded and scheduled for verified removal.
- Explicitly separated the personal FounderOS code repository from the work
  GitHub organization used as a workspace source.
- Rebuilt the authenticated shell around `Сейчас / Компания / Спросить` with
  one backstage `Настройки` entry. The dashboard now leads with one conclusion,
  up to two following situations and one obvious question action.
- Added `/ask` as a full evidence-backed assistant workspace. It uses the exact
  company snapshot, keeps conversation history in memory only, and performs no
  provider call, persistence or external write.
- Moved GitHub product setup to `/settings/integrations/github` and removed the
  product routes `/connectors`, `/github`, `/jira`, `/gmail`, and `/drive`.
  GitHub callback fallback navigation now returns to the settings route.
- Removed runtime `/demo`, synthetic Command Center components, Today/Living HQ
  browser models, the old mini-map, provider-first pages, superseded tests and
  their unused CSS/message blocks.
- Removed five unreachable frontend panels for legacy local sync, selected-repo
  sync, repository audit and source coverage together with their dead API
  clients, browser-only types, copy, styles and tests. Backend operator/audit
  foundations remain available outside the product navigation.
- Updated the offline MVP audit to recognize the consolidated integration
  settings surfaces without reintroducing provider-first pages.

## 2026-07-23

### Added

- Added the workspace integration control center at
  `/settings/integrations` (DEC-092). Owners and administrators can configure
  GitHub, Jira Cloud, Gmail, and Google Drive, apply an encrypted credential,
  run an explicit bounded read check, and inspect a safe write-readiness
  dry-run. Members and viewers retain a status-only view.
- Added `connector-control.v1` endpoints under the existing workspace connector
  router. Configuration writes reuse `IntegrationConnection`, keep safe
  receipts in `provider_metadata.control_center`, and add no schema migration.
  The status read never decrypts credentials; API responses expose no token,
  encrypted field, raw provider payload, connection UUID, or installation ID.
- Added the integration control reference covering the provider matrix, API
  contract, runtime gates, state model, and remaining OAuth/write gaps.

### Changed

- Rebuilt `/github` as one state-driven workspace (DEC-094). Disconnected,
  incomplete, connected and empty-repository states now expose one obvious
  action each. The setup wizard is opened explicitly and replaces the original
  connect CTA instead of competing with a command center, progress strip,
  metrics and repository-card filters.
- Replaced the separate GitHub “work pulse” with repository-scoped
  «Задачи» / «Pull requests» tabs and one status selector. A connected source
  has one repository selector and one read-only update button; viewer mode keeps
  facts visible without setup or sync controls. Technical details, warnings and
  the no-write/token-persistence facts remain available under disclosure.
- Rebuilt the integration screen as a minimal save → read-check workflow.
  Provider tabs are compact, checks stay disabled until configuration exists,
  empty receipts are omitted, and write readiness, credential removal, and the
  GitHub PAT fallback are progressive details. Unconfigured Radar cards now
  deep-link to the exact provider tab. Jira, Gmail, and Drive data pages use
  localized empty states and keep manual JSON import collapsed.
- Made local startup idempotent. A repeated `make local` recognizes a verified
  running supervisor and returns the existing product URL successfully;
  `make local-doctor` reports app ports owned by that exact repository runtime
  as healthy. Occupied unowned ports still fail closed.
- Closed a cross-workspace GitHub inventory fallback (DEC-093). Product reads
  now use canonical repositories from the exact workspace or return an empty
  inventory; unscoped `SourceEvent`, discovery-snapshot, and legacy fallbacks
  remain available only to explicit operator/script reads.
- Added a direct “Интеграции и API” entry to Settings. GitHub App remains the
  recommended GitHub path, while a personal token is an advanced fallback.
  Jira is restricted to exact HTTPS `*.atlassian.net` origins; Gmail and Drive
  honestly accept expiring manual OAuth access tokens until a complete
  authorization-code and refresh flow is implemented.
- Defined “write check” as readiness-only. It evaluates stored credential,
  successful read, write feature, approval and repository allowlist gates
  without decrypting the credential or calling a provider. External GitHub
  mutation remains available only through the existing exact approved
  ActionProposal execution boundary.
- Completed the credential lifecycle and response privacy boundary. An
  owner/admin can now remove a control-center credential after a second UI
  confirmation without deleting the durable connection row, imported canonical
  data, or sync history; a managed GitHub App is unaffected when its separate
  PAT fallback is removed. Every workspace connector response is
  `private, no-store` at the ASGI boundary, including auth, validation and
  application errors; a failed read receipt reports
  `provider_call_performed=false` when validation stopped before the network
  boundary. GitHub disconnect confirmation now distinguishes a standalone PAT
  from a PAT fallback attached to an active managed GitHub App.

## 2026-07-22

### Added

- Added the real deterministic company assistant (DEC-091). The
  workspace-scoped `POST /api/v1/workspaces/{workspace_id}/assistant/query`
  reads the exact shared Headquarters snapshot, requires the caller's visible
  `expected_snapshot_id`, and returns bounded allowlisted intents, normalized
  citations, suggestions, optional safe navigation, partial/warnings metadata,
  `is_live=true` and `llm_used=false`. It persists no conversation, calls no
  provider/LLM and performs no mutation. Per-user/workspace rate limiting,
  identical-query single-flight, timeout/size bounds, prompt-injection tests,
  RBAC/tenancy checks and safe citation filtering protect the backend boundary.
- Added the frontend runtime dependency security gate (DEC-090). CI now runs
  `npm audit --omit=dev --audit-level=moderate`; CodeQL scans
  JavaScript/TypeScript in addition to Python and GitHub Actions; Renovate now
  tracks `web/package.json` with the same three-day stability delay as Python.
  Contract tests pin these supply-chain expectations without calling providers
  or reading secrets.

### Changed

- Replaced the Headquarters-only placeholder with one authenticated-shell
  assistant launcher across product zones. `Cmd/Ctrl+K`, overlay focus restore,
  strict runtime response validation and internal/external citation navigation
  are preserved. Headquarters registers its exact visible snapshot; other
  zones fetch the same server projection. A stale query returns
  `409 snapshot_changed`, clears the old answer, refetches and requires an
  explicit retry. «Сделай сам» only links an authorized reviewer to the
  existing human confirmation screen and never creates, approves or executes a
  proposal.
- Updated Next from `16.2.9` to `16.2.11` and constrained its vulnerable
  transitive PostCSS and Sharp packages to patched `8.5.21` and `0.35.3`.
  React was intentionally left unchanged. A clean lockfile install resolves the
  expected versions and reports zero runtime npm advisories.
- Corrected the Roadmap's stale Alembic-head reference to the actual single head
  `c5d6e7f8a9b0` and aligned the security baseline with the current dual
  browser-session/operator authentication boundary.

## 2026-07-17

### Added

- Added the version-bound local proposal decision contract (DEC-089). Exact
  single approve/reject commands require an idempotency key and deterministic
  `ap1_*` proposal version, may bind to the visible `hqs1_*` Headquarters
  snapshot, re-check current active membership/admin authority in the write
  session, lock the workspace proposal row and return a durable audit-backed
  receipt with `external_write_performed=false`. Same-input replay returns the
  existing receipt; conflicting key reuse, stale version/snapshot and invalid
  transitions fail with `409`. This command creates no execution, provider
  call, external write or migration.

### Changed

- Completed the local Headquarters exact-review loop. Mission detail now keeps
  unproven owner/customer/due/impact fields explicit, exposes field-level
  provenance separately from general evidence and opens only exact opaque
  Company Map profiles. Malformed, foreign or stale selectors fail closed
  instead of showing the company profile. The employee/customer drawer renderers
  separate product access from unconfirmed business role and use only durable
  relations plus exact bounded touchpoints. The current production Headquarters
  projection does not yet emit confirmed mission owner/customer relation IDs,
  so that end-to-end navigation remains an explicit schema/data gate; unresolved
  world candidates are the exact profile path currently reachable from HQ.
  Proposal missions open one
  compact role-aware local decision modal; pending work locks duplicate
  navigation, ambiguous transport results retry the same exact POST once with
  the same idempotency key and accept only its authoritative receipt, and a
  saved receipt remains visible if the subsequent Headquarters refetch fails.
  External preview/execute stays outside this modal and behind its existing
  separate human gate.

## 2026-07-16

### Added

- Added the LC-03 detailed onboarding read at
  `GET /api/v1/workspaces/{workspace_id}/headquarters/onboarding`. It slices the
  same `headquarters.v2` service and content-addressed snapshot as the compact
  Headquarters block, with `onboarding.v1`, five evidence-derived steps,
  required/recommended semantics, role-aware actions, ETag and private/no-store
  headers. Unknown or partial facts remain unresolved; the Python and browser
  validators reject any step state that contradicts its evidence.
- Added the first real unified Headquarters read contract (DEC-086):
  `GET /api/v1/workspaces/{workspace_id}/headquarters` composes existing
  canonical company, source, briefing, proposal and membership state inside one
  PostgreSQL `REPEATABLE READ, READ ONLY` transaction. It returns a
  content-addressed snapshot/ETag, deterministic priority and bounded queue,
  fixed three-metric pulse, source health axes, computed required/recommended
  onboarding, current-snapshot signals, evidence/provenance and backend
  capabilities. Missing, foreign, unresolved and soft-deleted evidence cannot
  enter evidence-backed ranking; public callers cannot claim system/AI origin
  or supply trusted severity. Typed backend and runtime-validated browser
  contracts plus tenancy/RBAC/precision/partial/boundary regressions precede UI
  adoption. Source history is aggregated, the Headquarters Company World path
  reads only the newest 100 Gmail records and matching resolution keys,
  proposal ranking scans at most 100 rows, and 64 KiB UTF-8 JSON caps prevent
  new oversized action payload/evidence fields. Legacy oversized proposals are
  counted but excluded before ORM materialization with honest partial/lower-
  bound coverage. Exact proposal deep links fetch the selected workspace row
  independently from the bounded list. Exact evidence selectors are provider-
  coherent and cannot fall back to looser refs; source-health missions use
  aggregate provenance; spoofed Gmail payload sources cannot manufacture
  cross-source correlation; malformed evidence URLs are omitted. A real
  Company World statement timeout is isolated by savepoint and returns typed
  partial while unknown DB/invariant errors still fail closed. This read slice
  adds no migration, provider call, LLM, secret read, acknowledgement or write.
- Added DEC-087 and the future SF-00 checklist for one modular Source Foundry
  intake/promotion plane. Provider adapters feed an immutable envelope/manifest,
  validation/quarantine, versioned normalization, conservative resolution and
  atomic canonical promotion with lineage/receipt. It is explicitly not one
  server per source, not a second knowledge source of truth and not a runtime
  feature or migration in this slice.
- Added `docs/LIVING_COMMAND_CENTER_CHECKLIST.md`, the end-to-end execution and
  acceptance ledger for turning the synthetic `/demo` command center into the
  real authenticated local product. It maps current foundations and gaps, locks
  the minimal `HeadquartersSnapshot` shape, and orders onboarding, source
  radars, exact mission/profile drill-down, persisted changes, read-only
  assistant, human-approved decisions, privacy, observability, desktop QA, and
  release proof. DEC-086 makes one server-side read projection the shared truth
  boundary for the UI, assistant, and post-receipt refresh; the first ticket
  explicitly adds no migration, provider call, LLM, or write.

### Changed

- Replaced the separate browser-computed onboarding journey with one compact
  setup modal over the real authenticated Headquarters (DEC-088). Workspace
  users entering `/onboarding` continue in `/dashboard`; zero-workspace accounts
  retain the explicit recovery surface without workspace reads. The modal shows
  one server-selected blocker, benefit, evidence disclosure and role-aware
  action, takes priority over every drawer/assistant overlay, resumes from the
  server snapshot after reload and refetches after completion. Explicit query
  intent is consumed without reappearing on workspace change, and the dark
  stage uses a high-contrast focus indicator. The old source/map/team fan-out,
  browser readiness derivation and six-step production journey were removed.
- Replaced the authenticated `/dashboard` browser-composed Today board with the
  real workspace-scoped Headquarters snapshot. The production surface now shows
  one server-ranked priority, exactly three pulse metrics, at most two queued
  missions and three current-snapshot signals, with source health, coverage,
  evidence and mission detail behind one accessible drawer shell. CTA targets,
  disabled reasons, precision and partial/stale truth come from the backend;
  stale workspace responses are ignored, in-flight reads are aborted on scope
  change, and no demo fixture, browser ranking, provider call, LLM or external
  write was added. The FounderOS assistant entry is explicitly a navigation
  shell until the separate read-only assistant contract lands.
- Replaced the 12-scene `/demo` tour with one desktop Living Command Center
  (DEC-085). The default surface now budgets attention to one priority, three
  pulse metrics, at most two next decisions, three recent signals, and one
  contextual FounderOS assistant launcher. Sources, evidence, people, customer
  history, documents, and queue detail open in a single overlay drawer; the
  decision context, exact preview, explicit confirmation, and receipt share one
  focused modal. The assistant is session-only and deterministic over the
  existing synthetic NovaFlow fixtures, exposes citation chips, and can navigate
  to context or prepare the demo decision without executing it. `Cmd/Ctrl+K`
  opens the same assistant instead of adding a separate command surface.
  Completing the simulation still changes `3/2/7` to `2/2/8`, promotes the next
  priority, prevents duplicate execution, and records only `DEMO-*`/`SIM-*`
  values with `externalWrite=false`. The exact-path production gate, disabled
  dashboard prefetch, permanent invented-data label, and API/provider/storage/
  external-write isolation from DEC-084 remain unchanged. The presentation
  outline, autoplay, scene navigation, guide rail, browser-window mock, and
  related dead styles/tests were removed. The stale-test-output cleanup now
  drops compiled tests whose TypeScript source was renamed or deleted.
- Finished the command-center interaction loop after independent review. Every
  next-decision row now opens its own mission card instead of a generic queue,
  exact source keys drive both counts and the orbit, and the promoted mission
  becomes the new primary action while the Atlas receipt stays secondary.
  Reset clears post-result assistant claims; team detail follows the active
  mission; overlay-to-overlay navigation preserves the original focus target;
  the receipt is announced on state change; and the desktop type floor was
  raised so progressive disclosure, rather than 8–9 px copy, carries density.

## 2026-07-15

### Changed

- Added the desktop-only `/demo` product simulation (DEC-084). Twelve interactive
  scenes now demonstrate the intended completed loop from onboarding and four
  source radars through a connected signal, Living Headquarters, relationships,
  customer/key-person and team profiles, knowledge, briefing, a human decision,
  safe preview, synthetic receipt, and the resulting headquarters/queue update.
  The surface includes scene deep links, browser history, visited progress,
  hints, manual exploration, timed presentation, fullscreen mode, and keyboard
  controls. Its NovaFlow data is deterministic and permanently labelled as
  invented. Direct final-scene navigation stays an unsaved preview; an explicit
  demo confirmation alone moves the queue from `3/2/7` to `2/2/8`, and completed
  decisions cannot be repeated accidentally. The exact `/demo` path is public in
  development and requires `FOUNDEROS_DEMO_ENABLED=true` in production; the exit
  link disables dashboard prefetch. No API/provider call, form submission,
  persistence, external URL/write, backend, schema, DB, RBAC, or LLM path was
  added. The acceptance contract is desktop 1280×720 only; no mobile/tablet claim
  is made.
- Rebuilt `/actions` as the Missions decision room (DEC-083). One bounded
  mixed-status window of at most 100 proposals now feeds a compact queue and one
  active decision console; pulse metrics describe that loaded window and stay
  stable while local status/origin filters change. The active mission alone
  owns its why-now context, consequences, evidence, approve/reject controls,
  external preview, and history. Changing missions resets transient execution
  confirmation state; an in-flight preview/history/write locks mission filters,
  workspace switching, and the global navigation shell. Stale responses from a
  previous workspace are ignored, and a sanitized successful outcome stays
  pinned in the active console through the background refresh. A later audit
  history read failure is reported separately and cannot downgrade the already
  confirmed execution into a retryable action error. Bulk review is
  revealed only after a consequence check;
  mutation failures remain inline and filter/selection states are keyboard- and
  screen-reader-readable. Existing ActionProposal RBAC, local decision audit,
  evidence, receipts, and explicit external-write approval boundary are
  unchanged. No backend API, schema, database, provider call/write, external
  action, or LLM path changed.
- Promoted `/company-brain` into the full Living World operating surface
  (DEC-082). A compact company command bar, real contour metrics, one current
  review rail, local zone filters, the spatial Company Map, and a contextual
  profile inspector replace the previous stack of page header, mission strip,
  coach text, board, and profile. Existing human-approved candidate resolution,
  durable affiliation, evidence, window, idempotency, and viewer/member RBAC
  behavior remains unchanged. Candidate totals, interactions, and candidate-
  organization people counts from a truncated window use lower-bound notation;
  a zero result is explicitly limited to the shown window. `Штаб` mini-map selections and evidenced
  candidate missions now open the exact full profile through a workspace-scoped
  opaque selector; raw email/domain-shaped Company Map keys never enter the URL,
  and stale/foreign selectors safely resolve to no entity. Touchpoints remain
  local history of the routed parent profile, and stale candidate versions fall
  back before an invalid profile can paint. The canonical Company Brain/entity
  layer now mounts only when its disclosure opens. Authenticated
  browser acceptance passed at 1280×720, 800×800, and 390×844 without horizontal
  overflow; mobile controls are at least 44 px. No backend API, schema, provider
  call/write, external action, RBAC, or LLM path changed.

## 2026-07-14

### Changed

- Introduced the Living Headquarters product model (DEC-081). The authenticated
  shell now has three everyday zones — `Штаб`, `Мир`, and `Миссии` — while
  providers and system controls stay backstage as `Радары` and `Настройки` and
  remain reachable on mobile. `/dashboard` now leads with one evidence-aware
  mission, a plain-language explanation, a compact interactive Company World,
  a current-snapshot signal feed, and a small world pulse instead of a wall of
  panels and abstract counters. The screen reads existing Company Map,
  connector, briefing, and ActionProposal state only. It distinguishes missing,
  empty, partial, role-limited, and truncated data; proposal refs are labelled as
  declared source references rather than verified backend facts; and the current
  snapshot is not called a since-last-visit delta. Pending proposals are loaded
  through a dedicated status-filtered request so older missions are not hidden
  behind recently completed items; the target Missions page now repeats its
  active status in the server request instead of filtering a mixed recent page
  in the browser. Partial reads no longer produce a false "no signals" empty
  state, and mobile focus follows the visible content before the fixed bottom
  navigation. No backend API, schema, provider call/write,
  RBAC, LLM path, or autonomous execution was added.
- Added the workspace-managed GitHub App self-service wizard (DEC-080). An
  owner/admin can now complete the primary setup from `/github`: create a
  private App from an exact read-only manifest, install it, verify ownership
  through App JWT plus OAuth/PKCE `/user/installations`, and save an explicit
  repository subset. Migration `c5d6e7f8a9b0` adds encrypted App credentials,
  verified installation facts, and a resumable setup session; raw state and
  temporary OAuth/installation tokens are not persisted. Connection activation
  rechecks a non-expired active relation, keeps only the saved inventory subset,
  and live read rejects repositories outside it. The managed read-gate exception
  is browser-session-only; operator/CI remains behind the global connector gate.
  GitHub denial is recoverable in the UI, viewer stays read-only, provider writes,
  webhooks, background sync, LLM, and hosted changes remain disabled. The
  env/manual path remains fail-closed compatibility only. Connected admins can
  revise GitHub access and repository selection without disabling the working
  subset before atomic save; another owner/admin may continue that completed
  setup. Managed provenance cannot fall back to legacy env authorization after
  credential deletion. The wizard now stacks on mobile, announces phase changes
  and moves keyboard focus, hides management affordances from viewers, and
  replaces legacy env instructions with direct UI guidance. No real GitHub App
  was created and no provider read was executed by this code change.
- Replaced the technical `/github` scaffold with a Source Command Center
  (DEC-079). The page now leads with a role-aware mission, shows the three-step
  path from GitHub App through one selected repository into FounderOS, and uses
  only truthful loaded-sample metrics for connection state, repositories,
  active repositories, last recorded sync, tasks, and pull requests. A compact
  repository chooser promotes one read-only load action; successful and partial
  loads refresh the visible work pulse and produce an honest no-write receipt,
  while pending and failed jobs remain recoverable attention states. Long repository
  and work lists collapse after a small preview, while readiness, env names,
  token/write policy, provenance, warnings, and technical causes remain
  available in disclosures. The redesign also closes a readiness bug that could
  make sync appear available for a non-connected installation. Backend APIs,
  persistence, RBAC, provider-read approval, external-write, and LLM boundaries
  are unchanged. Authenticated visual QA passed on real local data at 1280×720
  and 390×844 without horizontal overflow.
- Reworked the authenticated product into a mission-first Command Mode
  (DEC-078). The five primary zones now lead with «Сейчас → Нажмите →
  Результат»: Today keeps one compact mission, Company World teaches the first
  interaction and surfaces the next candidate, Actions puts the decision queue
  and next available step before creation/readiness tooling, Connectors
  recommends a useful source and its outcome, and Settings leads with the team
  and human-readable roles. Contextual hints and progressive disclosures keep
  forms, filters, evidence, and technical boundaries available without
  presenting another admin console. The account control is now a compact
  profile menu. This is frontend-only; backend APIs, persisted state, RBAC,
  provider-read gates, external-write approval, and LLM boundaries are
  unchanged.
- Allowed the local sign-in screen to accept a short login identifier instead
  of enforcing browser email syntax. The authentication API and session model
  stay unchanged; credentials remain local database state and are never written
  to tracked files.
- Made the one-command local runtime the active FounderOS operational path
  (DEC-077). `make local-doctor`, `make local`, `make local-smoke`,
  `make local-backup`, and `make local-stop` now define the founder-facing
  lifecycle: reuse a healthy loopback PostgreSQL or start a safe Compose
  fallback, preserve `.local/` and database volumes, apply migrations, run
  FastAPI/Next.js on loopback through the same-origin proxy, open returning
  login or private first-founder enrollment, verify bounded local health, create
  a restore-proven database plus raw-storage backup bundle, and stop recorded
  processes safely.
  Redis is optional for the current synchronous product path.
- Completed LOCAL-01 live acceptance on the current machine: doctor, local
  start and same-origin smoke passed; authenticated onboarding and all five
  product zones passed without overflow or console errors; ephemeral QA data
  was removed. The verified receipt restored 31 tables / 7 265 rows and checked
  51 files / 72 directories / 1 353 141 bytes, proved the real stored credential
  1/1 while excluding 3 fixtures, and used a private Unix socket with TCP
  disabled. `SIGHUP` cleanup and simulated supervisor `SIGKILL` followed by
  verified orphan recovery both passed.
- Added `docs/operations/local-runtime.md` as the canonical start, acceptance,
  backup/restore, recovery, and troubleshooting runbook. Removed the obsolete
  active private-beta/Railway runbooks and placeholder hosting templates;
  historical Railway rehearsal facts remain below and in git history. Removed
  the stale `PrivateBetaReadinessPanel` from Dashboard so the product no longer
  sends the founder toward a retired hosted checklist.
- Superseded DEC-039 and the Railway-specific topology wording of DEC-042 while
  preserving its first-party same-origin session property on loopback. A future
  hosted target now requires a new explicit decision.
- Changed the prerequisite for the first GitHub App real read and the one-action
  external-result smoke from a hosted deploy to a verified local stack. Provider
  reads, external writes, and LLM execution remain separately human-approved.
- Hardened the canonical local boundary: startup now refuses enabled LLM,
  write, or real-connector gates; every GitHub network path fails closed before
  credential decrypt/token mint/client use when real connectors are disabled;
  and local smoke accepts only plain loopback origins and never follows HTTP
  redirects that could carry an API key off-machine.
- Hardened local secrets and private storage. Bootstrap generates and preserves
  a dedicated encryption key without printing it, writes `.env.local`
  atomically as `0600`, disables the retired browser dev-key surface, and keeps
  `.local/` plus legacy raw storage at `0700`.
- Upgraded `make local-backup` from archive readability to a full private
  bundle: database and raw-storage checksums, raw content digests,
  aggregate-only manifest, isolated matching-major PostgreSQL restore/count
  comparison, verified cleanup, and a `0600` receipt. Current-head restarts do
  not create duplicate backups; pending/unknown migrations fail before upgrade
  unless this proof succeeds.
- Repointed the deterministic MVP completion audit from hosted deployment to the
  local full-stack runtime and made its scope explicit. The repository-only
  audit keeps runtime/provider gates separate by design. LOCAL-01 now supplies
  the independent live runtime proof; GitHub connect, first scoped sync, and the
  first real external result remain unproven.
- Documented the irreversible retirement gate: moving FounderOS local does not
  authorize stopping hosted services, removing domains, or deleting a database,
  volume, or project. A matching-major logical archive, checksum, isolated
  restore proof, observation window, and separate explicit approval are required
  before each external retirement phase.

## 2026-07-13

### Changed

- Replaced the registry-like Company World frontend with a spatial strategy
  board (DEC-076): the founder's company is central, while team, confirmed
  network, and discovery candidates occupy distinct contours. Confirmed people
  are grouped under organizations only from exact durable affiliation fields
  plus a human-authored relationship; name/domain similarity is never drawn as
  fact. A focused inspector shows profile-local touchpoints, with evidence and
  technical capability/window/warning details behind collapsed disclosures.
  Candidate resolution now asks one plain-language question at a time while
  retaining member+/viewer roles, candidate versions, idempotency, and server-
  resolved evidence. This frontend-only slice adds no backend API, migration,
  provider call/write, or LLM path. Local acceptance passed: 272 frontend tests
  plus typecheck/lint/build (17 routes); 537 backend tests plus Ruff and Alembic
  head/current/check; desktop 1024/1280 px and mobile 390×844 browser QA without
  overlap/overflow and with keyboard focus, 44 px controls, complete
  organization/person resolution, and zero console warnings/errors. Ephemeral
  QA data was removed. The offline sanitized `make release-handoff` gate passed
  on a clean exact commit without deploy, provider calls, secret reads, database
  access, or external writes.
- Added guided invite-only founder enrollment (DEC-075). An operator-created
  one-time `/start` URL now creates the founder, company workspace, owner
  membership, and browser session in one transaction. The database stores only
  the invite SHA-256 digest, expiry, and optional consumption/revocation
  receipts; TTL is capped at 168 hours. The bearer is fragment-only, HTTPS is
  required outside loopback, and a leaked unconsumed invite can be revoked by
  UUID. Expired/reused/revoked links fail generically, concurrent consumption
  creates exactly one identity, and Argon2 runs only after the invite and
  identity conflicts pass cheap checks.
- Hardened teammate setup links to `/setup-password#token=...`: query-token
  fallback was removed, the browser clears the address after capture, token and
  user rows are locked against concurrent password/session creation, invalid
  tokens never reach Argon2, and public input lengths are capped. All session
  creation paths store only printable User-Agent metadata up to 512 characters.
  A brand-new teammate now always receives exactly one setup link and chooses
  their own password; the inviter can no longer submit `initial_password`.
  Existing accounts with membership outside the target workspace are not
  attached silently: provisioning returns `409`, and a user-row lock guarantees
  that concurrent A/B workspace attachment yields at most one success. Delivery
  remains manual over a trusted channel; recipient acceptance/email delivery is
  deferred.
- Hardened public login availability and identity handling. Production rejects
  excessive per-client, global, or concurrent work before Argon2 through a
  process-local admission controller, while the durable database throttle stays
  per submitted email. Unknown, disabled, and passwordless accounts perform one
  stable dummy Argon2 verification; a correct credential still succeeds and
  resets an attacker-induced email lock, disabled users' existing sessions are
  revoked, password inputs are bounded before hashing, and stale throttle rows
  are pruned at most hourly with a 24-hour default retention. The admission
  contract is deliberately single-process; trusted client-IP behavior behind
  the deployment proxy remains a required pre-public-deploy smoke gate.
- Added a focused `/onboarding` journey whose progress is computed from the
  current workspace, canonical Company Brain source-record count, evidence-
  backed Company Map, and memberships. Skips remain pending, configured sources
  without records are not called ready, and failed reads remain unknown. The
  current step is hash-backed, with explicit return links from Sources and
  Settings; no decorative completion flag is persisted.
- Replaced the 11-link technical shell and dashboard panel wall with five
  product zones («Сегодня / Компания / Решения / Источники / Настройки»), nested
  provider routes, explicit multi-company selection, mobile bottom navigation,
  and a deterministic «Сегодня» screen with one next move plus three signals.
  The public login/enrollment surfaces now share the same company-management
  visual language. Source setup/import/sync and action review/execution are
  owner/admin; briefing generation, local action creation, and Company World
  resolution are member+; viewer remains read-only. Local import,
  human-triggered provider-read, and approval-gated external-write boundaries
  remain explicit.
- Added durable Company World profiles and founder confirmation (DEC-074).
  Workspace-owned `people`, `organizations`, `affiliations`, `interactions`,
  and terminal `company_world_resolutions` receipts preserve tenant-scoped
  provenance. `GET .../company-map` merges confirmed profiles with unresolved
  candidates; member+ may call `POST .../company-map/resolutions`, while viewer
  remains read-only and cross-workspace access stays hidden.
- Confirmation is server-resolved and idempotent: candidate versions detect
  stale projections, idempotency keys prevent duplicate writes, and client
  attempts to supply canonical email/evidence are rejected. Confirmed Gmail
  interactions persist sanitized metadata and source-record links only; raw
  records are never rewritten and no provider call, external write, or LLM is
  started.
- Added founder-facing confirm/dismiss controls, manual relationship and
  organization classification, confirmed profile sections, and explicit
  read-only viewer states to «Мир компании». Added aggregate-only Company World
  backfill with dry-run default and explicit apply; unconfirmed candidates are
  never auto-promoted. The schema requires every membership-origin person to
  reference a workspace membership. Downgrade takes exclusive table locks
  before its empty-table checks and refuses to drop non-empty profile tables.
- Added Company World v1 (DEC-073): a new workspace-membership-gated,
  workspace-scoped `GET /api/v1/workspaces/{workspace_id}/company-map` read
  model and product
  surface over workspace memberships plus sanitized Gmail metadata. It renders
  company and people profiles, external-contact and corporate-domain candidates,
  evidence links, and an email touchpoint timeline without claiming that a
  candidate is a customer, employer, or decision maker.
- In the initial DEC-073 projection slice, limits and privacy became explicit:
  the API reports available and considered Gmail message counts, the
  newest-100 window, order, and `truncated`; derived summary fields are named
  `*_in_window`. Raw bodies and snippets are excluded and cross-workspace
  isolation is tested. That projection-only slice added no table, migration,
  provider call, sync, external write, secret read, or LLM; DEC-074 above adds
  the later member+ local relationship-write boundary while viewer stays
  read-only.
- Reframed the product UI as company management: `/dashboard` is now «Штаб
  компании» with daily move, decisions, company map, and operational perimeter;
  `/company-brain` is «Мир компании»; the sidebar is grouped by command center,
  management, sources, and system. Existing operational panels remain available,
  while the globally scoped repository-audit overview is no longer mounted on
  the workspace dashboard.
- Retired the unsafe legacy `/audit` product route. The underlying filesystem
  Company Brain preview endpoints are now operator-key-only and reject even a
  valid browser session, preventing global local snapshots from being exposed
  as workspace product data. Workspace-scoped action audit/import APIs are
  unchanged.
- Updated the offline MVP completion contract to require the evidence-backed
  Company World surface instead of the retired global Repo Audit page. The
  current tree remains locally complete while deployment and the first real
  external action result remain human-gated.

## 2026-07-07

### Changed

- Added a sanitized private-beta release handoff report. New
  `scripts/private_beta_release_handoff.py` (also exposed as
  `make release-handoff`) combines local git state, the offline MVP completion
  audit, GitHub App real-read preflight, and the remaining human-gated next
  steps into one operator-facing report. It is offline/read-only except for
  local git metadata and starts no deploy, provider call, provider write,
  external write, database access, secret read, or LLM.
- Added `docs/deploy/external-action-result-smoke.md`, a manual,
  human-approved runbook for the final MVP flow step "Approve Action Proposal ->
  See External Action Result". It documents the one-action external-write smoke
  boundary, preconditions, preferred UI path, API fallback placeholders,
  idempotency/receipt checks, result sync, cleanup/rollback boundaries, and the
  required post-smoke return to read-only mode. It is linked from README and
  docs index and is explicitly excluded from normal read-only smoke, CI, deploy,
  provider-read, provider-token setup, and LLM paths.
- Added a deterministic offline MVP completion audit. New
  `app/services/mvp_completion_audit.py` maps every playbook §1.5 MVP
  requirement and every §1.4 main-flow step to authoritative in-repo evidence
  (specific files plus structural markers) and reports which items are locally
  complete versus human/external gated. A safe CLI
  `scripts/mvp_completion_audit.py` prints the same report (`--json` supported),
  and `tests/test_mvp_completion_audit.py` pins the contract. The audit is
  read-only and offline: no provider calls, network, database, deploy, external
  write, secret read, or LLM. It reports `local_scope_complete = True` for the
  current tree while keeping `fully_complete = False` because staging/prod
  deployment and the first real external action result remain human-gated.
- Aligned high-level control docs with the current implemented state. README,
  `founderOS_MASTER_PLAYBOOK.md`, and `docs/ROADMAP.md` no longer describe
  local Jira/Gmail/Drive/Documents, teammate provisioning/setup links,
  normalized entities, request logging, or the prior guarded GitHub issue live
  smoke as missing; they now distinguish those completed local/MVP surfaces from
  the remaining human-gated gaps (first GitHub App real read, production deploy,
  LLM narrative, live non-GitHub provider sync, and broader beta hardening).
- Added a `/github` GitHub App real-read readiness section. The product connect
  panel now mirrors the existing offline preflight using already-loaded local UI
  state: app env configured/missing, workspace-scoped installation connection
  state, local repository surface count, blockers, and the next human step. The
  section is display-only and starts no sync, provider read, provider write,
  secret read, external write, or LLM; the actual real read remains the existing
  explicit per-repository action after human approval.
- Added a founder-facing action review readiness summary to `/actions`. The
  `ActionProposalsPanel` now computes local counts for proposals needing a
  decision, approved GitHub issue proposals ready for execution preview,
  local-only internal follow-ups, proposals missing evidence refs, and proposals
  with a reported execution receipt, plus a deterministic next-step hint. This
  is frontend-only over the already-loaded local proposal list and starts no
  execute call, sync, provider call, external write, secret read, or LLM.
- Added basic application request logging (DEC-072, MVP §1.5 "basic logging").
  New `app/core/logging.py` provides an idempotent `configure_logging()` and a
  `RequestLoggingMiddleware` that logs one sanitized line per HTTP request
  (method, path, status, duration_ms) at the `FOUNDEROS_LOG_LEVEL`/`LOG_LEVEL`
  level (default `INFO`); `app/main.py` configures it at startup and installs the
  middleware. The logger never records query values, headers, cookies, bodies,
  tokens, or provider payloads, so no secrets can leak. No new dependency,
  table, migration, provider call, external write, or LLM.
- Added a dedicated navigable Company Brain view (DEC-071, MVP §1.4/§1.5). New
  `/company-brain` page and sidebar entry compose the existing read-only
  `CompanyBrainPanel` and `NormalizedEntitiesPanel` with a manual refresh, so the
  founder can reach the canonical evidence-backed Company Brain and normalized
  entities directly (playbook "See Company Brain entities") instead of only
  scrolling the dashboard. No new data path: read-only, no provider calls, sync,
  external writes, secret reads, or LLM.
- Added a client-side entity-type focus filter to the normalized-entities panel
  (DEC-071 polish). The founder can switch between all entities and each
  `entity_type` in the already-loaded projection; filtering is local-only and
  starts no provider call, sync, external write, or LLM.
- Added a read-only normalized-entities projection API (DEC-070, MVP §1.5 /
  §6.9). New service `company_brain_entities_read_service.py` and endpoint
  `GET /api/v1/workspaces/{workspace_id}/company-brain/entities` flatten the
  canonical Company Brain rows (repositories, issues, pull requests, Gmail
  messages, Drive files, internal documents) into a single evidence-backed
  `entities` list plus a by-type/by-provider summary. It builds the canonical
  `/brain/entities` surface DEC-028 named as the trigger for revisiting
  NormalizedEntity, without a new table/migration and without producing the
  post-MVP `Person` entity. Read-only and local-only: no provider calls, sync,
  external writes, secret reads, or LLM.
- Added a dashboard UI surface for the normalized-entities projection (DEC-070).
  New `NormalizedEntitiesPanel` fetches the entities endpoint, shows summary
  cards, type/provider breakdowns, the evidence-backed entity list, source refs,
  and explicit no-provider/no-LLM boundary copy. This makes the MVP "See Company
  Brain entities" path reachable from the product UI instead of only the API.
- Extended briefing-derived local action generation to internal document context
  (DEC-069). The persisted briefing
  `POST /workspaces/{workspace_id}/briefings/{briefing_id}/action-proposals`
  endpoint now treats `internal-document-context` as an evidence-backed
  actionable item alongside Jira/Gmail/Drive briefing signals, creating a local
  `internal_todo` ActionProposal when evidence exists and skipping duplicate
  open actions for the same briefing item. Local-only: no provider calls, sync,
  external writes, raw document body copying, secret reads, or LLM.
- Wired in-product edit and delete for internal Documents (DEC-066/DEC-068).
  The `/documents` detail view now exposes an inline edit form (title, markdown
  body, tags, status) backed by the existing `PATCH
  /api/v1/workspaces/{workspace_id}/documents/{document_id}` route and a guarded
  delete affordance backed by the existing `DELETE` route. A successful edit
  refreshes the document and its version history, so document version history
  can now grow past version 1 through the product UI (previously only create was
  reachable). Local-only: no provider calls, external writes, secret reads, or
  LLM.
- Added local version history for internal Documents (DEC-068). New
  `document_versions` table + migration `f2b3c4d5e6f7` records an immutable
  snapshot on document create and every successful update, preserving title,
  markdown body, deterministic body text, status, tags, author, and version
  number. Empty or idempotent PATCH requests are treated as no-op updates and
  do not append duplicate history revisions. The Documents API now exposes
  `GET /api/v1/workspaces/{workspace_id}/documents/{document_id}/versions`, and
  `/documents` detail now renders selectable version snapshots with markdown
  body, status, tags, and recorded timestamp instead of only a compact list.
  Local-only: no provider calls, external writes, secret reads, or LLM.

## 2026-07-06

### Changed

- Added internal-document context to deterministic Founder Briefings (DEC-067).
  Manual briefings now include `internal-document-context` when Company Brain
  contains internal documents under `documents.notes`, with evidence refs from
  the internal document source refs. The item uses bounded metadata (titles,
  statuses, tags) and does not copy raw markdown/body text; local-only with no
  provider calls, sync, external writes, secret reads, or LLM.
- Added the internal Documents module (DEC-066, MVP §1.5 / §4.7 / §6.16 / §7.11).
  New workspace-scoped ``documents`` table + migration ``f1a2b3c4d5e6``, a
  member-gated CRUD + search API (``/api/v1/workspaces/{id}/documents`` and
  ``/documents/{document_id}``), and a ``/documents`` frontend page (list,
  search, create, detail) with a sidebar entry. Documents store authored
  ``body_markdown`` plus a deterministic plain-text projection for search, and
  non-archived documents now appear in Company Brain under ``documents.notes``
  with evidence refs. Local-only: no provider calls, external writes, secret
  reads, or LLM.
- Added deterministic local action-proposal generation from persisted Founder
  Briefings (DEC-065). The backend now exposes
  `POST /workspaces/{workspace_id}/briefings/{briefing_id}/action-proposals`
  to create evidence-backed local `internal_todo` ActionProposal rows from the
  Jira/Gmail/Drive briefing items, and the Briefing UI has a bulk local action
  generation control. The path skips missing-evidence items and existing open
  actions for the same briefing item (including older per-item UI actions) and
  remains local-only: no provider calls, sync, external writes, secret reads, or
  LLM.
- Added first-class local Jira/Gmail/Drive read-model items to the deterministic
  Founder Briefing (DEC-064). The manual briefing now includes
  `jira-work-items`, `gmail-message-signals`, and `drive-file-signals` when the
  workspace Company Brain has local Jira issues, Gmail messages, or Drive files.
  Items are evidence-backed from Company Brain `source_refs` and remain
  local-only: no provider calls, sync, external writes, raw body/content payload
  rendering, secrets, or LLM. Item summaries report the true imported total from
  the `source_records` aggregate ("N shown of M imported") instead of only the
  truncated visible slice, and visible-only unread/shared counts are scoped with
  "in view" so a capped section never implies a false workspace-wide total.
- Exposed Gmail messages and Google Drive files as first-class Company Brain
  read sections (DEC-063). Company Brain now returns `communications.messages`
  and `documents.files` built from sanitized local SourceRecord payloads, and
  the UI renders both sections separately from tasks. This keeps Gmail/Drive out
  of `Task` semantics while showing imported emails/documents in the founder
  surface. Local-only: no provider calls, sync, external writes, raw body/content
  rendering, secrets, or LLM.
- Promoted local Jira issues into Company Brain work items (DEC-062). Workspace
  Company Brain now includes canonical Jira `Task(source_provider='jira')` rows
  in `work.issues`, `work.recent`, issue summary counts, and evidence, with
  optional work-item `source_provider` and `project_key` fields for the UI. This
  is local/deterministic only: no Jira provider calls, sync, external writes,
  raw payload rendering, or LLM.
- Added a deterministic connector source-coverage item to the Founder Briefing
  (DEC-061). The manual briefing now surfaces a `connector-source-coverage`
  item from the Company Brain `source_records` aggregate so local
  Jira/Gmail/Drive imports are visible in the briefing flow, not only on the
  dashboard. Company Brain is fetched once per generation and shared with the
  existing GitHub-first coverage item. Aggregate-only: no raw payloads, provider
  calls, sync, external writes, or LLM.
- Added local connector SourceRecord coverage to the workspace Company Brain
  payload and dashboard Source Coverage panel (DEC-060). Company Brain now
  returns aggregate `source_records` counts by provider and record type so
  local Jira/Gmail/Drive imports are visible without exposing raw payloads,
  email bodies, document contents, secrets, provider calls, sync, external
  writes, or LLM behavior.
- Added the third minimal connector implementation: Google Drive (DEC-059). The
  backend now exposes local-only Drive file list/import endpoints, and the
  frontend adds `/drive` with a pasted/exported JSON import form. Imported file
  metadata is sanitized into canonical `SourceRecord` rows (file record type)
  with evidence refs through idempotent upserts; raw document bodies are not
  persisted. The path remains local DB-only: no Drive provider calls, no sync,
  no external writes, no LLM, and no secret reads. The connector registry now
  marks Google Drive `available`.
- Added a second minimal connector implementation: Gmail (DEC-058). The backend
  now exposes local-only Gmail message list/import endpoints, and the frontend
  adds `/gmail` with a pasted/exported JSON import form. Imported messages are
  sanitized into canonical `SourceRecord` rows (message record type) with
  evidence refs through idempotent upserts; raw email bodies are not persisted.
  The path remains local DB-only: no Gmail provider calls, no sync, no external
  writes, no LLM, and no secret reads. The connector registry now marks Gmail
  `available`.
- Added the first minimal Jira connector implementation (DEC-057). The backend
  now exposes local-only Jira issue list/import endpoints, and the frontend adds
  `/jira` with a pasted/exported JSON import form. Imported issues are sanitized
  into canonical `SourceRecord` + `Task` rows with evidence refs through
  idempotent upserts. The path remains local DB-only: no Jira provider calls, no
  sync, no external writes, no LLM, and no secret reads.
- Added the connector framework registry (DEC-056). The backend now exposes
  `GET /api/v1/workspaces/{workspace_id}/connectors`, and the frontend adds a
  `/connectors` page plus sidebar entry. The registry lists the MVP provider set
  (GitHub, Jira, Gmail, Google Drive), shows local connection counts, and
  explicitly remains read-only: no provider calls, sync, external writes, LLM,
  or secret reads. GitHub was available at introduction; Jira, Gmail, and Drive
  were later made available through DEC-057/058/059.

## 2026-07-03

### Changed

- Added local one-time account setup links for teammate onboarding (DEC-055).
  Admin provisioning can generate a `/setup-password` link without sending
  email or calling an identity provider; the database stores only the sha256
  token hash in `account_setup_tokens`. The public setup page consumes the token
  once, lets the teammate set a local password, signs them in, and rejects token
  reuse. Full pytest now uses a unique unknown-login email to avoid stale
  login-throttle state between full-suite runs.
- Enabled provisioned teammates to actually sign in (DEC-055). The workspace
  members endpoint and `/settings` provisioning form now accept an optional
  initial local password (min length 8) that is Argon2-hashed for a brand-new
  user, and the response reports `login_credential_set`. An existing user's
  password is never overwritten, so re-provisioning cannot hijack an account.
  Still no email invite, identity-provider write, or external write is performed.
- Added product UI for local teammate provisioning in `/settings`. The page now
  lists workspace members and lets owner/admin users create local
  `admin`/`member`/`viewer` memberships through the existing workspace members
  API, while viewer/member roles see a read-only state. The UI explicitly states
  that no email invite, identity-provider write, provider call, or external write
  is performed.
- Added the first local teammate-provisioning foundation (DEC-055). Workspace
  owners/admins can list members and create local `admin`/`member`/`viewer`
  memberships through workspace-scoped endpoints without sending email, calling
  an identity provider, granting `owner`, or performing external writes. Tests
  cover listing/provisioning, duplicate handling, disabled-user rejection, and
  role gating.
- Added an offline readiness gate for the first approved GitHub App real read
  run (DEC-054): a pure `github_app_real_read_run_readiness()` function, a safe
  presence-only CLI `scripts/github_app_real_read_run_preflight.py`, offline unit
  tests, and a human-approved read-only runbook
  `docs/deploy/github-app-first-real-read-run.md`. The readiness check performs
  no provider calls, opens no network connection, and emits no secret values;
  the real read run itself remains the existing human-triggered, repository-scoped
  sync endpoint.
- Added deterministic "what to check next" guidance to the `/dashboard`
  source-coverage panel. The panel now derives local next steps from the already
  loaded Company Brain payload for canonical data readiness, evidence gaps,
  open-work review, live-provider boundaries, and AI boundaries. This remains
  read-only dashboard copy: no new endpoint, provider call, external write,
  deploy, or LLM is started.
- Enriched the `/dashboard` source-coverage panel with a local breakdown built
  only from the already-loaded Company Brain payload: closed issues / merged PRs,
  recent activity count, repositories with vs. without source refs, and an
  evidence-by-kind breakdown. No new endpoints, provider calls, external writes,
  or LLM are added; the panel stays deterministic and read-only.
- Hardened the external repo-audit import UX on `/audit`. The paste-JSON form
  now renders a non-throwing local preview of parsed findings before import,
  marks each finding valid/invalid against the same rules the backend enforces
  (`repository_full_name` in `owner/repo` format plus at least one
  `evidence_ref`), and shows per-finding validation issues. Reviewers can
  select all valid findings or clear the selection, and only selected valid
  findings are submitted. After a partial backend import, per-finding backend
  failures are shown inline on the matching preview rows (including when only a
  selected subset was submitted) and only the failed rows stay selected for retry
  while the pasted text is preserved. Secret-like fragments are still redacted in
  the preview, and the import continues to write only local `internal_todo`
  ActionProposals with no provider calls, external writes, or LLM.
- Polished audit-origin action review on `/actions`. Audit-derived local
  proposals now distinguish deterministic repository-audit findings
  (`source=repo_audit`) from imported external-audit findings
  (`source=repo_audit_import`) with a local "audit source" subfilter,
  source-specific badges, and richer payload metadata (audit type, repository,
  severity, area, recommended next step, and risk/related entities) without raw
  payload dumps. The new `/actions?origin=audit&audit_source=...` query focus,
  bulk selection, and default evidence drawer all follow the final visible
  subset and remain client-side/local only: no provider calls, external writes,
  or LLM.
- Added a repository-audit overview panel to `/dashboard`. It reads the existing
  local deterministic repo-audit endpoint plus local ActionProposals and
  summarizes the audit loop: repository count, total risk flags, discovery
  snapshot, and audit-derived action counts (total / deterministic / imported /
  proposed). It deep-links into `/audit` and
  `/actions?origin=audit&status=proposed` (plus
  `audit_source=deterministic|imported` when such actions exist). The
  action-proposal counts are supplementary and never break the deterministic
  audit summary if they fail to load. The panel is client-side/local only: no
  provider calls, external writes, or LLM.
- Expanded the private-beta readiness panel with a manual deploy/smoke runbook
  checklist. The dashboard now shows the explicit human-run phases from the
  deploy docs (local gates, Postgres backup, manual Alembic migration, split
  backend/frontend services, read-only smoke, and rollback boundary) without
  starting any command. This remains a local/read-only dashboard aid: no deploy,
  push, provider call, external write, production data mutation, or LLM is
  performed.

## 2026-07-02

### Changed

- Grouped the ActionProposals review list by proposal origin (from briefing
  items, GitHub issue proposals, and internal todos) with per-group counts and
  descriptions, and marked briefing-derived proposals with an explicit origin
  badge. Grouping is applied on top of the existing local status filter and
  makes no provider calls or backend state changes.
- Extended the shared evidence drawer with an optional contextual hint that
  distinguishes a default (first visible proposal) source from a manually
  selected one, plus an optional evidence-ref count. The briefing panel usage is
  unchanged and no raw payloads or secrets are rendered.
- Rendered briefing-derived `internal_todo` proposal payload metadata (briefing
  item key, category, severity, recommended next step, and related entities) in
  the ActionProposals detail view instead of only repository/title/note, without
  exposing raw payload dumps or secret-like keys.
- Added a local ActionProposals origin filter that composes with the existing
  status filter. Users can focus on all sources, briefing-derived proposals,
  GitHub issue proposals, or internal todos; counts are computed within the
  current status focus, and the evidence drawer default follows the final
  visible result set without provider calls, backend mutations, external writes,
  or LLM calls.
- Added bulk local ActionProposal review controls. Users can select all visible
  `proposed` proposals in the current status/origin filter intersection, clear
  the selection, and locally approve or reject the selected proposals through the
  existing local ActionProposal endpoints. Selection is pruned to visible
  `proposed` items so hidden, approved, or rejected proposals are not mutated by
  accident; provider execution, external writes, and LLM calls are not started.
- Hardened bulk local ActionProposal review against partial failures: each
  approve/reject is settled independently so already-applied local transitions
  are preserved and merged even if another proposal in the batch fails, the
  reviewer keeps only the failed proposals selected for retry, and a partial or
  total failure is surfaced inline without hiding the loaded list. Still no
  provider execution, external writes, or LLM calls.
- Added local backend bulk ActionProposal endpoints:
  `POST /actions/proposals/bulk-approve` and
  `POST /actions/proposals/bulk-reject`. They are admin-only, dedupe requested
  proposal IDs, return per-proposal successes/failures with counts, preserve
  partial success semantics, and never start provider execution, external
  writes, or LLM calls. The web bulk review controls now use these endpoints
  instead of issuing one request per proposal.
- Added local review decision audit events for ActionProposals. Single and bulk
  local approve/reject successes append sanitized audit events to the existing
  per-proposal audit timeline, with explicit no-external-write metadata and no
  `ActionExecution` rows or provider calls. The UI audit copy now labels the
  timeline as decisions and execution.
- Surfaced the recorded decision history in the UI for any decided proposal.
  `ActionExecutionControls` now shows a "Показать историю решений" control for
  approved or rejected proposals (including internal/briefing-derived ones) that
  loads the persisted per-proposal audit trail through the existing read-only
  audit endpoint. Previously the authoritative trail was only fetched via the
  approved-GitHub-issue execution preview, so decision history was unreachable
  for rejected or internal proposals. Read-only; no provider calls, external
  writes, or LLM.
- Added local category filtering and default evidence selection to the Founder
  Briefing UI. Briefing items can now be focused by category within the already
  loaded deterministic briefing, and the evidence drawer defaults to the first
  evidence ref from the visible items with briefing-specific context and counts.
  Manual evidence selection still overrides the default. No provider calls,
  external writes, or LLM calls are started.
- Enriched the Founder Briefing history cards with local coverage summaries and
  deltas against the currently open briefing. History now shows repo/work/evidence
  coverage and local/live mode per saved summary, plus item/evidence deltas when
  a briefing is open. This uses only the already-loaded persisted briefing
  summaries and starts no provider calls, external writes, or LLM calls.
- Cross-linked Founder Briefing items with existing local ActionProposals. The
  briefing screen now reads local proposal state, shows linked action counts by
  status, blocks blind duplicate local action creation for items that already
  have an open action, and links to `/actions` with briefing/proposed filters.
  This is local/read-only apart from the already existing `internal_todo`
  creation control and does not start provider calls, external writes, or LLM.
- Added a dashboard private-beta readiness panel backed by the existing
  Company Brain endpoint. It shows canonical data/evidence readiness, session
  login boundary, manual deploy runbook status, deferred GitHub provider reads,
  external-writes-off, and LLM boundary without deploying, pushing, calling
  providers, performing external writes, or invoking LLM.
- Added local repo-surface focus filters to the `/github` GitHub App panel.
  The already-loaded repository list can now be filtered by all, active,
  archived, private, or evidence-backed repositories with summary counts. This
  remains client-side only and does not call providers, start bulk sync, perform
  external writes, or weaken the explicit per-repository read-only sync path.
- Surfaced the deterministic repository audit in the founder UI. The existing
  `GET /api/v1/founder/company-brain/repo-audit` (computed locally from the
  GitHub discovery snapshot, no network, no writes) was previously unreachable
  from the product UI; a new `/audit` page and `RepositoryAuditPanel` now render
  per-repo audit facts, risk flags, summary counts, guardrails, and local focus
  filters (all/risks/stale/needs-confirm). Each repo can spawn an
  `internal_todo` ActionProposal marked `source=repo_audit` with audit evidence
  refs. ActionProposals review gained an `audit` origin (filter, group, badge,
  payload detail) plus cross-links back to repositories. This is read-only apart
  from the local proposal write and starts no provider calls, external writes,
  or LLM.
- Added a structured external repo-audit import path on `/audit`. Users can
  paste JSON findings from another/full audit result (array or
  `{ findings: [...] }`), and the backend endpoint
  `POST .../actions/proposals/import-repo-audit` turns valid entries with
  `repository_full_name` plus `evidence_refs` into local `internal_todo`
  ActionProposals marked `source=repo_audit_import` with per-finding partial
  failures. The import path redacts known secret-like fragments in imported
  text fields, writes only local proposals, and starts no provider calls,
  external writes, or LLM.

## 2026-07-01

### Changed

- Added GitHub App product-connect foundation: backend config/status contract,
  workspace-scoped app-installation connection recording without provider calls
  or persisted installation tokens, and a `/github` UI panel showing app
  readiness, local repository surface count, and external writes disabled.
- Hardened GitHub App installation endpoint test coverage: member/viewer RBAC
  rejection, idempotent same-installation update in place, and invalid
  `repository_selection` rejection. Test-only; no production behavior change.
- Added polling-only GitHub App live read-sync foundation: just-in-time
  installation token minting, installation repository read client, explicit
  repository-scoped issues/PRs read sync through the existing normalization
  path, and tests proving no token persistence or provider writes.
- Added `/github` product UI for explicit GitHub App read-only sync of one
  repository through the new backend endpoint, with no browser secrets and
  user-visible no-write/token-persistence boundaries.
- Fixed `scripts/create_admin_user.py` so direct local execution
  (`uv run python scripts/create_admin_user.py`) can import the project `app`
  package without manually setting `PYTHONPATH`.
- Refined the `/github` GitHub App sync UI to render each known repository with
  its own adjacent read-only sync button and per-repository success/error state;
  no bulk sync control was added.
- Added GitHub App synced-evidence verification coverage proving mocked live
  sync feeds Company Brain and deterministic Briefings with evidence while a
  second workspace cannot see the synced canonical state or evidence refs.
- Added sanitized GitHub provider error/rate-limit observability for live read
  sync: safe HTTP status/message/rate-limit headers propagate to API errors
  without leaking authorization headers, tokens, or provider payload dumps.
- Added an offline, idempotent local org repository ingest helper that promotes
  `.local/repos.json` into canonical workspace `Repository` rows so `/github`
  shows the configured organization's repositories instead of retained
  source-event or legacy fallback rows; the helper reads only the non-secret
  target-org setting from env files and does not read or print GitHub tokens.
- Added a dashboard Source Coverage panel backed by the existing Company Brain
  endpoint. It summarizes canonical repository/work/evidence counts and clearly
  labels live provider reads and LLM generation as deferred/off without making
  provider calls or AI calls.
- Extended deterministic Founder Briefings with local source-coverage signals
  and a `source-coverage` briefing item derived from Company Brain. Briefing UI
  now summarizes canonical repos, open work, evidence refs, and local/live mode
  without adding provider writes, provider reads, or LLM calls.
- Added a local-only Briefing → ActionProposal bridge: each briefing item can
  create an `internal_todo` proposal carrying that item's summary and evidence
  refs for later local approval, without creating GitHub issues or executing
  external writes.
- Added local status filters to the ActionProposals review panel so proposed,
  approved, rejected, and all local proposals can be reviewed without extra
  provider calls or backend state changes.
- Reworked the action execution audit UI into a structured local timeline with
  status, event, provider/action, timestamp, and external-write boundary per
  event, keeping raw provider payloads hidden.
- Defaulted the ActionProposals evidence drawer to the first evidence ref in
  the current local review filter, while keeping a safe placeholder for
  evidence-free proposals and avoiding provider calls.

## 2026-06-30

### Changed

- Added offline GitHub repository-surface preparation from `.local/repos.json`:
  repo audit and repository inventory now accept the root local repo list as a
  fallback discovery snapshot, and `scripts/prepare_github_local_snapshot.py`
  writes the canonical `.local/discovery/github/<snapshot>/raw/repos.json` layout
  plus a safe local repo allowlist snippet without provider calls or secrets.

- Added a DB-level GitHub repository identity guard:
  `uq_repositories_workspace_provider_full_name` on
  `(workspace_id, provider, full_name)`. Migration `e8f9a0b1c2d3` de-duplicates
  existing duplicate repository rows, re-points pull requests to the keeper, and
  makes repository upsert race-safe across the `external_id` and `full_name`
  paths before GitHub product connect/live sync.

## 2026-06-29

### Changed

- Persisted deterministic Founder Briefings: `Briefing` / `BriefingItem` tables
  and history endpoints now store/reopen generated manual briefings while the
  generator remains deterministic and LLM-free. New single Alembic head:
  `e7f8a9b0c1d2`.
- Audited the active documentation set and clarified the source-of-truth matrix
  in `docs/README.md`. `docs/TODO.md` was reduced from a completed-work ledger
  to a near-term backlog focused on GitHub product connect/live sync before LLM
  briefing narrative.
- Updated `README.md`, `PROGRESS.md`, `docs/ROADMAP.md`,
  `founderOS_MASTER_PLAYBOOK.md`, `AGENTS.md`, and `CLAUDE.md` to reflect that
  deterministic Founder Briefings are now persisted and that current LLM rules
  remain forward-looking.
- Added documentation-maintenance rules for future agents and Make convenience
  targets for backend, frontend, combined checks, and tracked-secret scan.
- Expanded `.gitignore` for common generated/cache/build artifacts.

### Removed

- Removed three obsolete grouped-lifecycle operator scripts that were no longer
  referenced and failed import because their required report module had already
  been removed in earlier cleanup.

## 2026-06-28

### Added

- Email+password founder login on server-side, revocable sessions. Added
  `password_service` (Argon2id), `session_service` plus a `sessions` table (the
  DB stores only the sha256 hash of the cookie token), and the auth endpoints
  `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`,
  and `POST /api/v1/auth/change-password` (the last revokes other sessions). New
  `require_session` dependency and a `get_current_actor` resolver that accepts
  either a session cookie (preferred) or the operator API key.
- DB-backed login brute-force throttle (`login_attempts` table): after a
  configured number of failures an email is locked for a configured window;
  known and unknown emails throttle identically and the API returns a generic
  error. Tunable via `FOUNDEROS_LOGIN_MAX_FAILED_ATTEMPTS` /
  `FOUNDEROS_LOGIN_LOCKOUT_MINUTES`.
- Idempotent admin provisioning command `scripts/create_admin_user.py` (seeds the
  single founder/admin user from `FOUNDEROS_ADMIN_*` env vars; re-running updates
  the password without creating a duplicate).
- Same-origin Next.js proxy so the session cookie stays first-party across the
  split frontend/backend deploy: `web/next.config.mjs` rewrites `/api/*` and
  `/health` to `FOUNDEROS_API_PROXY_TARGET` (falls back to
  `NEXT_PUBLIC_API_BASE_URL`).
- A `/login` page, `AuthGate`, session client (`web/lib/auth.ts` /
  `web/lib/session.ts`), and a Settings→account / change-password page.
- Canonical-task uniqueness: a partial unique index
  `uq_tasks_workspace_provider_external_id` (`workspace_id`, `source_provider`,
  `external_id` where `external_id IS NOT NULL`) plus dedupe migration
  `f7b8c9d0e1a2`.
- Central Russian UI message catalog `web/lib/messages.ts`.

### Changed

- GitHub normalization upserts (`Task`, `PullRequest`, `SourceRecord`,
  `Repository`) are now idempotent via PostgreSQL `INSERT ... ON CONFLICT DO
  UPDATE`, fixing duplicate rows on re-sync. `Task.updated_at` is documented as a
  "last synced" marker (bumped every sync); user-facing recency uses
  `source_updated_at`.
- The frontend no longer uses browser operator-key/owner-email config
  (`web/lib/config.ts` removed); workspace is derived from the session, and
  browser requests carry neither the operator key nor `owner_email`.
- Connector-token encryption now fails closed outside local/dev unless a
  dedicated `FOUNDEROS_SECRET_ENCRYPTION_KEY` is set (no longer reuses the API
  auth key as encryption material outside local).
- Public health split: `GET /health` is a minimal no-auth liveness probe; env
  and feature-flag detail moved to `GET /health/detail` behind the operator key.
- Account-active state reuses `User.status` (`active`/`disabled`); no `is_active`
  boolean was added.
- `ingested_events` Alembic drift reconciled (migration `a8c9d0e1f2b3`, indexes
  and constraints only — no data change). New single Alembic head:
  `c0e1f2a3b4d5`.
- Decisions recorded as DEC-041…DEC-047 in `docs/DECISIONS.md`.

### Safety

- The DB stores only session-token hashes; passwords are Argon2id-hashed and
  never returned. The admin-provisioning command never prints the password. No
  external provider writes, deploy, or push were part of this phase.

## 2026-06-27

### Security

- FOS-027B1 — private-beta blocker hardening pass 1. Made API auth fail-closed
  outside local: `enforce_fail_closed_auth` aborts backend startup when a
  non-local `APP_ENV` runs with auth disabled or without a configured API key
  (env-var names only in errors, never values). Added a shared frontend
  `safeHref` helper plus a `SourceLink` component so untrusted, server-provided
  URLs (evidence/source URLs, `external_result_url`) render as anchors only for
  http(s); `javascript:`/`data:`/`vbscript:`/malformed values render as
  non-clickable text. Removed stale `app/agents` bytecode and reconciled
  CLAUDE.md / SECURITY_BASELINE.md / README.md references to deleted LLM/agent
  code and a deleted boundary doc. No deploy, no push, no provider writes.

### Changed

- Bootstrapped the minimal private-beta workspace/owner context in the deployed
  Railway database through the supported operator workspace bootstrap API, then
  ran the full read-only deployed smoke successfully across health/auth,
  workspace read, GitHub connection status read, Company Brain read,
  operational work read, and deterministic transient briefing generation.
  Provider writes, selected repo live sync, ActionProposal execute, LLM, and
  real connectors remained disabled/not called; secret values and operational
  IDs are intentionally omitted.
- Ran the authenticated Railway private-beta setup/rehearsal: created the
  rehearsal project with backend, frontend, and managed Postgres services; Redis
  was skipped. Backend/frontend deployments reached success, Railway Postgres was
  migrated to Alembic head, backend health/frontend load/CORS/API auth behavior
  were verified, and read-only deployed smoke passed in health/auth-only mode.
- Updated the Railway runbook/templates with rehearsal findings: current Railway
  Railpack requires `RAILPACK_BUILD_CMD`/`RAILPACK_START_CMD`, and backend
  runtime `DATABASE_URL` must use the `postgresql+asyncpg` driver form while
  local operator migrations use the public Postgres URL only inside the
  subprocess environment.
- The earlier workspace-scoped deployed-smoke blocker was resolved by FOS-026C
  using the supported operator bootstrap API. Provider writes, LLM, real
  connectors, selected repo live sync, and ActionProposal execute remained
  disabled/not called. Secret values are intentionally omitted.

## 2026-06-26

### Added

- Added `docs/deploy/railway-private-beta.md`, selecting the Railway-only
  split-service private-beta dry-run target implied by the master playbook. The
  plan maps backend API, frontend web, managed Postgres, managed/deferred Redis,
  service commands, domain/CORS/API-base, env names, migration dry run, smoke
  dry run, rollback dry run, operator checklist, and later live-provider-smoke
  approval boundaries without provisioning or deploying.
- Added placeholder-only Railway backend, frontend, and smoke env templates under
  `docs/deploy/templates/`, plus hosting-doc safety tests for required sections,
  placeholder-only values, no secret-shaped values, no auto-deploy workflows,
  and no provider-write/sync commands.

- Added `docs/deploy/private-beta.md`, a manual private-beta deploy runbook for
  the split backend API process, frontend web process, managed Postgres, and
  managed/deferred Redis model. The runbook documents backend/frontend commands,
  migration verification, backup and rollback policy, required env names,
  CORS/API-base setup, GitHub connection boundaries, and read-only post-deploy
  smoke.
- Added deploy-doc safety tests covering required env names, required commands,
  DB/migration/rollback documentation, read-only smoke/provider-write
  boundaries, absence of secret-shaped values, and absence of auto-deploy
  workflow commands.

- Added FOS-025C frontend/full-stack deploy-readiness CI gates. The CI workflow
  now has separate backend and frontend jobs: backend keeps the existing secret
  scan, dependency sync, ruff, Alembic upgrade, and full pytest gates while
  explicitly running docs/smoke/CORS/CI contract tests; frontend runs `npm ci`,
  `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint` from
  `web/`.
- Added CI deploy-readiness contract tests that assert frontend gates exist and
  the workflow does not include live smoke, selected repository sync,
  ActionProposal execute, provider-token setup, or provider secret usage.

- Added the FOS-025B private-beta deploy/smoke foundation: explicit backend
  CORS settings, placeholder-only env template, read-only private-beta smoke
  script, `make smoke`, and local/private-beta run documentation.
- The smoke script checks only safe health/auth/workspace/read-model endpoints
  plus deterministic manual briefing generation, and forbids ActionProposal
  execute, selected repository sync, provider-token setup, local-sync,
  normalize-local, post-execution-result sync, and provider write endpoints.
- Added focused tests for CORS config, smoke endpoint safety, no API-key output,
  placeholder-only env examples, and docs env-name coverage.

### Changed

- Added read-only selected repository sync controls to the product dashboard
  (`SelectedRepositorySyncControls`) near the existing GitHub sync, Company
  Brain, and operational work panels.
- The controls discover the GitHub connection id from the existing
  connection-status endpoint instead of hardcoding it, validate an explicit
  `owner/repo` repository name client-side (non-empty, single slash, no
  spaces), and call the existing selected issue and PR sync endpoints
  read-only, one explicit allowlisted repository at a time.
- Added typed frontend API helpers `syncSelectedRepositoryIssues`,
  `syncSelectedRepositoryPullRequests`, and a combined
  `syncSelectedRepositoryGitHubWork`, plus request/response types for selected
  issue and PR sync.
- The controls render missing-settings, missing-connection, invalid-input,
  per-action loading, success summaries (repositories synced; issues
  synced/open/closed; PRs synced/open/closed/merged; skipped PR-shaped issue
  records), backend allowlist/permission/generic errors, and empty/no-records
  states; they show explicit read-only / no-external-write copy and avoid raw
  JSON and private identifiers.
- A successful selected sync refreshes the Company Brain and GitHub operational
  work panels through the existing dashboard refresh signal; no backend
  contract change was required and no GitHub write is performed.
- Added read-only selected repository pull request sync under the GitHub
  workspace namespace:
  `/api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
- Selected PR sync requires the explicit read-sync repository allowlist before
  token decrypt/provider reads, fetches only selected repositories with a
  read-only GitHub pulls client, and normalizes open/closed/merged PRs into
  canonical `SourceRecord` + `PullRequest` records through the existing GitHub
  normalization path.
- Selected PR sync keeps repository identity stable after selected issue sync,
  so the same `owner/repo` repository row is reused instead of creating a
  duplicate; PR read models also de-dupe by repository and PR number.
- Selected PR sync is covered with read-only provider mocks for the approved
  repository scope and performs no GitHub issue, PR, comment, merge, close, or
  other provider write.
- Added read-only selected repository issue sync under the GitHub workspace
  namespace:
  `/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync`.
- Selected issue sync requires an explicit read-sync repository allowlist before
  token decrypt/provider reads, fetches only selected repositories, skips
  PR-shaped issue API records, and normalizes open/closed issues into canonical
  `SourceRecord` + `Task` records through the existing GitHub normalization
  path.
- Product GitHub issue read models now de-dupe alternate historical issue
  identifiers by repository and issue number so a real issue is not double
  counted in operational work or Company Brain.
- Selected issue sync was verified read-only against the approved smoke
  repository: one closed issue synced, open count stayed zero, ActionExecution
  receipt counts stayed unchanged, and no new GitHub writes occurred.
- Closed the approved smoke issue after explicit human approval and verified the
  closed state through the existing post-execution sync path.
- Closed-state sync updated canonical GitHub work records so operational work no
  longer counts the smoke issue as open, Company Brain sees the closed issue,
  and deterministic briefing remains evidence-backed.
- No additional GitHub issues were created and no comments, PRs, releases,
  labels, assignees, titles, bodies, repository settings, or other repositories
  were modified.
- Added a read-only post-execution sync route for executed GitHub issue
  `ActionProposal` receipts:
  `/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result`.
- The post-execution sync path validates an executed/succeeded receipt, reads
  the provider issue through the encrypted GitHub connection, creates a local
  manual SyncJob, and reuses canonical GitHub normalization to upsert
  `SourceRecord` + `Task`.
- Post-execution sync was verified for the gated live GitHub smoke issue:
  operational work and Company Brain see the synced issue, deterministic
  briefing reflects the normalization evidence, and no duplicate external
  execution occurred.
- Manual live GitHub issue smoke succeeded through the gated `ActionProposal`
  execution path against an approved private smoke repository.
- Exactly one GitHub issue was created; receipt and durable audit are stored
  locally; external issue URL/id are intentionally omitted from public docs.
- No other repositories were modified, and the next step is explicit smoke issue
  closeout/cleanup approval.

## 2026-06-25

### Added

- Added a non-secret live GitHub write repository allowlist for approved issue
  execution: `FOS_GITHUB_WRITE_ALLOWED_REPOS`, with `FOS_GITHUB_SMOKE_REPO` as
  a single-repository alias.
- Added durable `execution_repository_not_allowed` audit events for missing or
  non-matching write allowlists before any token decrypt or provider call.
- Added gated live GitHub issue execution behavior over the existing approved
  `ActionProposal` executor: runtime write capability, explicit confirmation,
  valid GitHub payload/connection, evidence refs, duplicate receipt return, and
  mocked-provider tests.
- Added durable execution attempt audit events for confirmation received,
  execution start, success, failure, block, and duplicate receipt return.
- Added frontend receipt rendering for successful external issue id/url and
  explicit live-write confirmation copy in `ActionExecutionControls`.
- Added proposal-scoped `action_execution_events` plus migration
  `a2b3c4d5e6f7` for durable, sanitized execution preview/blocked-attempt audit
  records.
- Added idempotent action execution audit helpers and
  `/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/audit`
  with a local execution receipt/readiness view.
- Added frontend audit-trail reads so `ActionExecutionControls` displays
  persisted audit events, local receipt state, and timestamp fallback when no
  events exist.
- Added dry-run GitHub issue execution preview endpoint at
  `/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execution-preview`.
- Added typed frontend helpers for action execution preview and explicit execute
  requests under the existing workspace action proposal namespace.
- Added `ActionExecutionControls` for preview-only execution readiness, external
  execution disabled state, missing-evidence warnings, fallback audit/status
  history, and explicit connection+confirmation UI when backend capabilities
  allow live writes.
- Added backend/frontend tests for execution preview URL/body contracts,
  disabled execution capability, confirmation gating, audit visibility, and no
  raw provider payload rendering.
- Added typed frontend helpers for local ActionProposal list, create, approve,
  and reject routes under
  `/api/v1/workspaces/{workspace_id}/actions/proposals`.
- Added `ActionProposalsPanel` for product local approval workflow: proposal
  list, manual local proposal creation, local approve/reject buttons, status
  summary, proposal audit timestamps, backend warnings, and evidence drawer
  links.
- Added frontend tests for action proposal URL/body construction, local
  approve/reject calls, unsupported transition errors, loading/missing/empty/
  unsupported/error states, evidence refs, and no external-write claims.

### Changed

- Live GitHub issue execution now blocks unless the target repository is
  explicitly allowlisted; broad token scope and variable names such as
  `READONLY` are not trusted as safety boundaries.
- Earlier bounded setup against an approved private smoke repository target was
  blocked by GitHub permissions, so no smoke candidate was prepared in that run
  and no real issue was created then.
- Live GitHub issue execution remains disabled by default and was not manually
  smoke-tested; automated checks use mocked provider/client boundaries only.
- Repeated execute on an already-succeeded proposal now returns the existing
  receipt without calling the provider again.
- Preview and blocked execute paths now record/reuse local audit events without
  calling GitHub or overloading `ActionExecution`, legacy `audit_logs`, or
  retained `source_events`.
- Blocked `/execute` when `enable_write_actions=false`, so approval and preview
  cannot silently cross into live provider writes in default environments.
- Wired `web/app/actions` and dashboard action panels to the guarded execution
  preview surface while keeping live writes capability-gated.
- Wired `web/app/dashboard` and `web/app/actions` to the local ActionProposal
  approval workflow while keeping external execution disabled in the UI.

## 2026-06-24

### Added

- Added typed frontend helpers for the manual deterministic Founder Briefing
  endpoint at `/api/v1/workspaces/{workspace_id}/briefings/manual`.
- Added `BriefingPanel` and `EvidenceDrawer` to render manual briefing
  sections, returned evidence refs, source links only when provided, and
  explicit no-live-provider/no-AI/no-action-execution boundaries.
- Added frontend tests for briefing URL/body construction, loading/missing/
  empty/unsupported/error/success states, evidence buttons, evidence drawer
  details, and avoidance of fake briefing/source data.
- Added `GET /api/v1/workspaces/{workspace_id}/company-brain`, a read-only
  deterministic Company Brain endpoint over canonical GitHub repositories,
  issue/task records, pull requests, and `SourceRecord` source refs.
- Added a dashboard Company Brain panel showing evidence-backed GitHub state,
  summary counts, repositories, open issue/PR highlights, recent work, source
  refs, and explicit no-live-provider/no-AI capability status.
- Added backend and frontend tests for the Company Brain GitHub evidence state,
  including empty state, canonical summary, evidence/source refs, ignored
  retained `source_events`, and UI loading/missing/error states.
- Added `POST /api/v1/workspaces/{workspace_id}/github/local-sync` as a compact
  product backend wrapper over existing manual SyncJob + local normalization
  behavior; it persists through the canonical local path and does not start live
  provider execution.
- Added dashboard GitHub local-sync controls that read connection status, show
  missing/unsupported/loading/error/success states, report normalized
  repository/issue/PR counts, and refresh canonical operational work after a
  successful local sync.
- Added backend and frontend tests for the local-sync control path, including
  no-live-provider flags, no-connection handling, idempotence, URL building,
  POST payload shape, and honest no-OAuth UI states.

### Changed

- Wired the dashboard and `/briefings` page to generate the existing manual
  deterministic Founder Briefing and inspect returned evidence refs.
- Wired the dashboard to canonical GitHub operational work from
  `/api/v1/workspaces/{workspace_id}/github/operational-work`, including
  issue/task and PR sections, repository labels, filters, and loading/empty/error
  states.
- Added a lightweight frontend test command for the `web/` shell using
  TypeScript compilation plus Node's built-in test runner.
- Fast-forward merged the cleanup/FOS-008/doc-hygiene line into local `main`
  at `ef22360`; `main` is ahead of `origin/main` until an explicit push.
- Collapsed the current control docs to
  `founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`, `docs/DECISIONS.md`,
  `docs/README.md`, `docs/ROADMAP.md`, `docs/TODO.md`,
  `docs/POST_MVP.md`, and `docs/CHANGELOG.md`.
- Marked FOS-009 as the next main-path task after FOS-008 canonical repository
  persistence.

### Removed

- Removed `EXECUTION_PLAN.md` from the active control set (DEC-031).
- Removed the live archive tree from the current docs set; historical material
  is recovered through git history / tag `pre-purge-20260624`.

## 2026-06-23

### Added

- Added root canonical docs for the incoming playbook line.
- Added this changelog as the missing required playbook control doc.
- Added `docs/README.md` as the single docs navigation entry.
- Added `docs/_audit/DOCS_AUDIT.md` before any archive/removal action.

### Changed

- Updated documentation navigation to make the root control docs the primary
  source of truth.
- Preserved current useful feature/runbook docs as supporting docs subordinate
  to the canonical playbook.
- Replaced large historical ledger docs at selected paths with slim current
  status / compatibility docs while archiving the originals.

### Archived

- Historical older playbook, vision, audit, dirty-tree, backlog, agent-stub,
  Telegram/manual-pilot, Jira rebuild, and ledger docs were later removed from
  the live tree by DEC-029/DEC-031.

### Safety

- No application code, tests, migrations, raw storage, generated Obsidian vault
  files, env files, or secrets were intentionally modified.
