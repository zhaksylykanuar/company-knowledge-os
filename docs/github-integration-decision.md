# GitHub Integration Decision for founderOS MVP

## 1. Purpose

The master playbook requires a GitHub-first MVP E2E: connect GitHub, sync
repositories/issues/PRs, show evidence-backed GitHub data in the product, create
a Founder Briefing, and execute one approved GitHub issue action.

The repository already has source-control request handling, guarded provider
actions, repository audit/read models, repository source inventory, and
read-only GitHub discovery surfaces. The canonical `IntegrationConnection` and
`SyncJob` database models now exist, and the backend has a workspace-aware auth
contract.

This document chooses the safest MVP path without rewriting working code,
duplicating source truth, or bypassing existing guardrails.

## 2. Current GitHub / Source Control Inventory

| Area/File | Current purpose | Reads? | Writes? | Guardrails | Tests | MVP decision |
|---|---|---|---|---|---|---|
| `app/services/source_control.py` + `app/db/source_control_models.py` | Source Control Center read model and local request lifecycle for test/sync/backfill/pause/resume actions. | Yes: DB source events, normalized activity, connector setup/status, request rows. | Local DB only: `SourceRunRequest`, `SourceControlState`, audit/request state. No provider calls. | Module states it never calls external connectors; masks connector readiness; idempotent request keys; source/action allowlists. | `tests/test_stage9_source_control.py`, source-control coverage in API route auth tests. | KEEP_AS_BRIDGE |
| `app/api/inbox.py` source endpoints | Founder/operator API for source health, source action requests, source-run receipts, and source-event reads. | Yes: DB source health/runs/events. | Local DB request rows for source actions. No external provider writes. | Protected by existing API-key wiring and founder-view guard; validates source type/action. | `tests/test_stage9_source_control.py`, `tests/test_api_route_auth.py`. | KEEP_AS_BRIDGE |
| `app/connectors/github.py` | Guarded GitHub raw-event connector primitives and synthetic/live transport contract. | Yes, through injected transport when allowed. | No DB writes and no external writes. | Live mode default-denied; exact live-provider ack required; sanitized diagnostics; raw-event envelope contract. | `tests/test_github_connector.py`. | ADAPT_LATER |
| `app/services/github_discovery.py` + `scripts/run_github_discovery.py` | GET-only GitHub discovery runner that saves local discovery artifacts and sanitized summaries. | Yes, GitHub GET only when explicitly confirmed and credentials exist. | Local `.local/discovery/github/...` artifacts only. No DB writes or external writes. | Confirm phrase, GET-only transport, bounded reads, secret scrubbing, safe stdout. | `tests/test_github_discovery.py`. | KEEP_AS_BRIDGE |
| `app/services/github_org_inventory.py` + `scripts/check_github_org_readonly_inventory.py` | Read-only GitHub org inventory and migration-readiness diagnostics. | Synthetic by default; live read-only only with ack/config. | No writes. | Live read-only ack, safe target-org normalization, count-class output, provider payload suppressed. | `tests/test_github_org_inventory.py`, `tests/test_github_org_readonly_inventory_cli.py`. | ADAPT_LATER |
| `app/services/repository_source_inventory.py` | Repository read model from `source_events`, then saved GitHub discovery snapshots, then legacy seed catalog. | Yes: DB source events and local discovery files. | No writes. | `read_only`, `network_calls=False`, `db_written=False`, output sanitizer. | `tests/test_repository_source_inventory.py`. | KEEP_AS_BRIDGE |
| `app/services/repo_audit.py` + `app/api/company_brain.py` repo-audit endpoint | Computed Company Brain repository audit over saved GitHub discovery snapshots. | Yes: local discovery snapshot and repository catalog. | No writes. | `preview_only`, `computed`, `db_written=False`, `network_calls=False`, no raw email, provenance labels. | `tests/test_stage28_repo_audit.py`, `tests/test_stage28_company_brain_repo_audit_api.py`, eval coverage. | KEEP_AS_BRIDGE |
| `scripts/sync_github_activity.py` | Compatibility helper that now records a sanitized Source Control sync request instead of directly calling GitHub. Pure fetch/map helpers remain for tests. | No provider read in the compatibility execution path. | Local Source Control request when run. | Required confirm phrase; compatibility live flags recorded as metadata only; tests assert no direct GitHub fetch. | `tests/test_github_graph_sync.py`. | KEEP_AS_BRIDGE |
| `app/services/github_graph_mapping.py` | Repository-to-graph mapping helpers for repo entities and `belongs_to` links. | Yes: graph rows. | Local graph rows when explicitly called. | Idempotent mapping; evidence refs; not an OAuth/product connection path. | `tests/test_github_graph_sync.py`. | ADAPT_LATER |
| `scripts/check_external_connectors_readonly.py` | Read-only GitHub/Jira connector smoke report. | Synthetic or live read-only with explicit ack. | No writes. | Default-deny provider execution, sanitized/count-style output, no source-of-truth mutation. | Connector readonly tests. | DO_NOT_TOUCH_NOW |
| `app/api/drive.py` and `app/api/gmail.py` Source Control delegation | Existing pattern for guarded provider routes delegating disabled/backfill flows to Source Control request rows. | Provider reads only in existing guarded route behavior. | Local request rows when delegated. | API-key protection, source-control request mode, connector path tests for unauthenticated/disabled flows. | `tests/test_drive_backfill.py`, `tests/test_gmail_backfill.py`, route-auth tests. | KEEP |
| `app/db/integration_models.py` | Canonical `IntegrationConnection` and `SyncJob` foundation for future product connection/sync paths. | Future ORM reads. | Future local DB writes. | Provider/status/sync_type constraints; token fields are encrypted by contract and never exposed. | `tests/test_integration_models.py`. | KEEP |
| `app/api/workspace_auth.py`, `app/api/workspaces.py`, `app/services/identity_service.py` | Workspace-aware API contract and operator-compatible bootstrap/access layer. | Yes: `User`, `Workspace`, `Membership`. | Local workspace/user/membership bootstrap. | Existing API-key/operator auth; explicit `owner_email` operator context; membership checks. | `tests/test_workspace_auth_contract.py`. | KEEP |

## 3. Options Considered

### Option A - Use existing Source Control as MVP bridge only

Pros:

- Lowest implementation risk.
- Uses already-tested request, guard, source-event, and repository inventory logic.
- Faster route to a GitHub read API and dashboard slice.

Cons:

- Does not fully match the canonical `IntegrationConnection`/OAuth model.
- Some surfaces are local/operator-oriented rather than productized.
- UI semantics could imply a finished connector path when it is still a bridge.

### Option B - Build canonical GitHub OAuth immediately

Pros:

- Closest match to the master playbook product flow.
- `IntegrationConnection` and `SyncJob` already exist.
- Establishes the right long-term product path early.

Cons:

- Larger blast radius: OAuth state/callbacks, secrets, scopes, token handling,
  workspace scoping, and error handling.
- Higher risk of breaking existing guarded provider/source-control flows.
- Delays the simpler workspace-scoped repository read API that can validate the
  source/evidence substrate first.

### Option C - Hybrid staged path

The existing Source Control and repository source layers remain a compatibility
bridge/read substrate. The canonical product path becomes
`IntegrationConnection` + `SyncJob`, but it is introduced in staged tasks:

- First expose a workspace-scoped GitHub repository read API from existing
  source/evidence layers.
- Then define and add GitHub connection routes on top of
  `IntegrationConnection`.
- Then add OAuth or token-based connection flow, depending on the accepted
  product/security convention.
- Then record manual sync jobs with `SyncJob`.
- Then normalize GitHub repositories/issues/PRs into the existing graph/source
  substrate or a documented compatibility layer.
- Only later add an approved GitHub issue write path through the action approval
  boundary.

## 4. Final MVP Decision

Decision: **Option C - Hybrid staged path**.

For MVP, existing Source Control is kept as a bridge/read substrate. It is not
the final product OAuth model, but it is useful, tested, and already guarded.

Canonical GitHub product connection work will use `IntegrationConnection` and
`SyncJob`. Those tables become the product path for GitHub connection/sync, but
they should not replace `source_control` in one rewrite.

Practical rules:

- Keep existing Source Control as bridge/read substrate for now.
- Use `repository_source_inventory` as the first repository read model for
  FOS-GH-02.
- Do not rewrite `source_control` now.
- Do not expand post-MVP source actions now.
- Build GitHub-first E2E in small staged tasks.

## 5. GitHub-first MVP Sequence

1. FOS-GH-02 - Workspace-scoped GitHub repository read API from existing source/evidence layer.
2. FOS-GH-03 - GitHub connection contract using `IntegrationConnection`.
3. FOS-GH-04 - GitHub OAuth start/callback or provider-token connection, depending on accepted conventions.
4. FOS-GH-05 - Manual GitHub sync job record using `SyncJob`.
5. FOS-GH-06 - Normalize GitHub repositories/issues/PRs into existing graph/source substrate or compatibility layer.
6. FOS-BRF-01 - Manual Founder Briefing v0 with evidence refs.
7. FOS-ACT-01 - Human-approved GitHub issue action proposal.
8. FOS-ACT-02 - Execute approved GitHub issue creation safely.

## 6. Boundaries / No-Go Rules

- No live provider calls without explicit approval.
- No external writes before the ActionProposal approval path exists.
- No direct frontend calls to GitHub.
- No broad rewrite of `source_control`.
- No new provider modules until the GitHub path works.
- No Jira write work before GitHub E2E.
- No Telegram/share-pack expansion.
- No multi-agent council, sandbox execution, or natural-language rule compiler now.
- No cleanup of existing source modules unless proven unused and separately approved.

## 7. Required Backend Contracts

### GitHub repository read API

- Purpose: return GitHub repositories from stored `source_events`, saved GitHub
  discovery snapshots, or legacy seed fallback without provider calls.
- Expected route: `GET /v1/workspaces/{workspace_id}/github/repositories`.
- Workspace access requirement: use `require_workspace_access`; operator mode
  uses explicit `owner_email` per FOS-BE-01.
- Input/query params: `owner_email` for operator compatibility, optional
  `source_class`, `include_legacy`, and pagination/limit if needed.
- Output shape: list of repositories with `repo_key`, `full_name`,
  `provider_key`, `source_class`, `last_observed_at`, `repo_role`,
  `repo_not_jira_project`, provenance/freshness, and evidence/source refs when
  available.
- Evidence/source references: include source event IDs or discovery snapshot
  metadata; never return raw provider payloads.
- Errors: unauthenticated, missing workspace access, invalid workspace ID,
  empty repository state, malformed local snapshot.
- Tests: workspace access required, operator `owner_email` context, no provider
  calls, empty state, missing access, provenance/source refs included.

### GitHub connection API

- Purpose: create/read the product GitHub connection contract for a workspace.
- Expected route: `POST /v1/workspaces/{workspace_id}/github/connections` and
  `GET /v1/workspaces/{workspace_id}/github/connections`.
- Uses `IntegrationConnection` with provider `github`.
- Does not expose tokens, encrypted token fields, or raw provider metadata.
- Errors: missing workspace access, duplicate active connection, unsupported
  provider status, disabled/revoked connection.

### GitHub sync API

- Purpose: record a manual GitHub sync intent for a workspace connection.
- Expected route: `POST /v1/workspaces/{workspace_id}/github/sync-jobs`.
- Creates `SyncJob` with provider `github`; no worker implementation unless
  separately scoped.
- Errors: missing workspace access, missing/disabled connection, unsupported
  sync type, duplicate in-flight sync if a later contract requires it.

### GitHub approved action API

- Purpose: later create a GitHub issue only after human approval.
- Depends on `ActionProposal` and `ActionExecution` or a reconciled existing
  approval layer.
- No direct writes before approval.
- External result must be audited and visible.

## 8. Data Model Mapping for GitHub

- GitHub account/installation/token -> `IntegrationConnection`.
- Sync run -> `SyncJob`.
- Repository -> future `Repository`, existing graph `repository` entity, or
  repository compatibility layer over source/inventory data.
- Issue -> future `Task`, existing source event, or compatibility layer.
- Pull request -> future `PullRequest`, existing source event, or compatibility
  layer.
- Provider raw response -> future `SourceRecord` or existing `source_events`
  bridge.
- Evidence -> existing evidence/source refs bridge, then future `EvidenceRef`
  compatibility.

No tables are added by this decision.

## 9. Tests Required for Next Task

For FOS-GH-02:

- Route requires workspace access.
- Operator `owner_email` context works according to FOS-BE-01.
- Route returns repository list from existing source/evidence layer.
- No provider calls.
- No external writes.
- Empty state is explicit and safe.
- Missing workspace access is rejected.
- Evidence/source refs or discovery snapshot refs are included when available.
- Response does not imply repository equals Jira project.

## 10. Risks

| Risk | Mitigation | Blocks FOS-GH-02? |
|---|---|---|
| `source_control` is not workspace-aware. | Do not use Source Control as the product connection model in FOS-GH-02; use workspace route/dependency and read-only inventory. | No |
| Static `/ui` assumes local/operator global data. | Keep FOS-GH-02 backend-only; Next.js/web shell remains separate. | No |
| Source/evidence compatibility is not canonical yet. | Use existing `repository_source_inventory` with provenance labels and document source class. | No |
| OAuth scopes/secrets are complex. | Defer OAuth to FOS-GH-04 after read API and connection contract. | No |
| Accidental live provider calls. | Tests must trap provider calls; use existing inventory/read model that reports `network_calls=False`. | No |
| Duplicate GitHub data paths. | Treat Source Control/discovery/source events as bridge; `IntegrationConnection`/`SyncJob` as product path. | No |

## 11. Final Recommendation

Ready for FOS-GH-02: YES.

Next task: FOS-GH-02 - Workspace-scoped GitHub repositories read API from existing source/evidence layer.
