# API Boundary Security Plan

## Status

- Endpoint-level auth: implemented for selected protected API routes
- Rate limiting: planned; boundary plan documented (deferred by design — no public exposure yet)
- Webhook signature validation: planned (deferred — no webhook routes exist yet)
- Write/action approval enforcement: implemented as a guard (FOS-007E); write endpoints/agents not built yet
- Read-only connector posture: implemented for Drive/Gmail wrappers; partial for future connectors

## Endpoint Classification

### Public/local

- `/health` can remain unauthenticated.
- Production health responses should be minimal and avoid exposing sensitive runtime detail.

### Internal/protected

These endpoints should require API key or equivalent auth outside local/dev:

- `/v1/events`
- `/v1/drive/backfill`
- `/v1/gmail/backfill`
- `/v1/knowledge/ingest-text`
- `/v1/knowledge/ingest-text-process`
- `/v1/knowledge/score`
- `/v1/extraction/*`

### Sensitive read endpoints

These endpoints should require auth outside local/dev:

- `/v1/knowledge/search`
- `/v1/knowledge/ask`
- `/v1/knowledge/attention`

### Future external webhooks

Future GitHub, GitLab, Bitbucket, Telegram, and Google webhook endpoints must validate provider signatures or secret tokens before persistence.

### Future write/action endpoints

Future write/action endpoints must:

- Require auth.
- Require explicit approval.
- Respect `enable_write_actions` and `require_approval_for_writes`.
- Never be directly triggered by LLM output.

The enforcement primitive for the last three now exists — see FOS-007E below.

## FOS-007E Plan — Write-Action Approval Enforcement

### Status

- Implemented as a pure enforcement guard: `app/services/write_action_guard.py`.
- No external write endpoints or source-agent write paths are wired yet; the
  guard is the gate any future write call site must pass through.

### Contract

Before any external write (Jira/GitHub) executes, the call site calls
`require_approved_write_action(...)`, which fails closed unless **all** hold:

1. `enable_write_actions is True` (the feature flag, default off).
2. When `require_approval_for_writes` (default on): a founder approval exists
   for **this exact write boundary** — an `AgentProposal`
   (`kind == "external_write_action"`) the founder accepted in the inbox, whose
   payload declares the `write_boundary`. Only `accepted`/`applied` statuses
   authorize; `pending`/`rejected` are blocked.
3. The live-provider execution ack is present (composes
   `provider_execution_guard.require_live_provider_execution_ack`).

Write boundaries are a closed registry distinct from read/event boundaries, so
a read ack can never authorize a write: `jira_create_issue`,
`jira_update_issue`, `jira_transition_issue`, `jira_comment_issue`,
`jira_create_project`, `jira_create_component`, `github_create_issue`,
`github_update_issue`, `github_comment_issue`, `github_create_pull_request`,
`github_update_repository`, `github_transfer_repository`.

### Flow

An agent that wants to write files a proposal (reusing
`agent_proposals.create_proposal` with the `external_write_action` kind) → the
founder accepts it in the existing inbox → the agent executes via
`require_approved_write_action`, building the approval with
`write_approval_from_proposal`. The full draft → approve → execute loop reuses
the existing proposal queue, audit trail, and reversibility fields.

### Security Invariants

- Diagnostics are sanitized: unknown boundaries collapse to
  `external_write_boundary`; no raw payload, provider content, or secrets are
  surfaced. Only the internal approval id (our own proposal id) is included.
- The guard is pure/synchronous — it makes no provider call and mutates
  nothing; it only decides whether a write may proceed.
- LLM output can file a proposal but can never grant approval or execute a
  write; approval is a human decision recorded against `AgentProposal`.

## Rate-Limit Policy

Rate limits are planned for:

- Ingestion endpoints.
- Webhook endpoints.
- Extraction endpoints.
- Ask/search endpoints.
- Score endpoints.
- A light global limit for health if needed.

## Secret/Logging Policy

- Never log `Authorization` headers.
- Never log API keys.
- Never log webhook signatures.
- Never expose secrets in tests or docs.
- Use `.env.example` for variable documentation only.

## Rollout Plan

- FOS-007: docs/security plan only.
- FOS-007A-docs-plan: document the auth config boundary and implementation split.
- FOS-007A-impl: add config flags and reusable API key dependency, without attaching it to routes.
- FOS-007B-docs-plan: document the route auth enforcement scope and implementation split.
- FOS-007B-impl: protect selected internal ingestion/extraction/knowledge endpoints.
- FOS-007C-docs-plan: document the rate limiting boundary and implementation questions.
- FOS-007C-impl-design: choose edge/app/shared-state strategy if needed.
- FOS-007C-impl: implement rate limiting only after explicit approval.
- FOS-007D: add webhook signature validation when webhook routes exist.
- FOS-007E: define write/action approval enforcement before any write endpoints.

## FOS-007A Plan

FOS-007A is split so planning stays separate from implementation:

- FOS-007A-docs-plan: this docs-only ticket.
- FOS-007A-impl: add auth-related config and a reusable API key dependency/helper, but do not attach it to routes.
- FOS-007B: attach the dependency to selected routes after explicit approval.

### Scope

- Add auth-related configuration without route enforcement.
- Add a reusable API key dependency/helper for later route wiring.
- Keep existing endpoint behavior unchanged until FOS-007B.
- Use existing FastAPI and Pydantic settings capabilities; add no new package unless proven necessary.

### Implementation Status

- FOS-007A-impl adds `api_auth_enabled`, `api_auth_key`, and `api_auth_header_name`.
- FOS-007A-impl adds a reusable API key dependency/helper for later route wiring.
- No production routes are protected yet.
- FOS-007B will attach the dependency to selected routes after explicit approval.
- No middleware, rate limiting, webhook signature validation, migrations, or new dependencies are added.
- No secrets are committed; configuration docs must use placeholders such as `API_AUTH_KEY=<set-in-environment>`.
- API key comparison uses constant-time comparison.
- Auth enabled without a configured key fails closed.

### Implementation Files

- `app/core/config.py`
- `app/api/auth.py`
- `tests/test_api_auth.py`
- `docs/security/api-boundary.md`
- `docs/backlog.md`

### Later Test Plan

- Config defaults keep local development non-breaking.
- Missing API key is rejected when the dependency is invoked.
- Wrong API key is rejected when the dependency is invoked.
- Valid API key is accepted when the dependency is invoked.
- Error messages and logs do not expose secret material.
- `/health` remains public when route enforcement is added later.

### Security Invariants

- Raw storage and Postgres remain the source of truth.
- Obsidian remains export-only.
- LLMs must not directly mutate production data.
- LLM pipeline outputs must remain strict JSON and validated before persistence.
- No secrets are committed to the repo; docs use placeholders such as `<set-in-environment>`.
- API key comparison must use constant-time comparison.
- Outside local/dev, auth must fail closed when enabled but the configured key is missing.

## FOS-007B Plan

FOS-007B is split so route enforcement is planned before implementation:

- FOS-007B-docs-plan: this docs-only ticket.
- FOS-007B-impl: attach the existing FOS-007A dependency to selected routes after explicit approval.
- Later tickets, only if explicitly approved: rate limiting, webhook signatures, and a broader auth or identity model.

### Scope

- Attach the existing FOS-007A reusable API key dependency/helper to selected production API routes in a later implementation ticket.
- Keep `/health` public.
- Use existing config: `api_auth_enabled`, `api_auth_key`, and `api_auth_header_name`.
- Add no new dependencies.
- Add no middleware.

### Candidate Protected Routes

- `/v1/events`
- `/v1/drive/backfill`
- `/v1/gmail/backfill`
- `/v1/knowledge/ingest-text`
- `/v1/knowledge/ingest-text-process`
- `/v1/knowledge/score`
- `/v1/knowledge/search`
- `/v1/knowledge/ask`
- `/v1/knowledge/attention`
- `/v1/extraction/*`

### Public Routes

- `/health`

### Expected Later Behavior

- Auth disabled: protected routes continue to behave as they do today.
- Auth enabled and configured key missing: protected routes fail closed with a generic auth error.
- Auth enabled and request key missing: protected routes reject the request.
- Auth enabled and request key wrong: protected routes reject the request.
- Auth enabled and request key valid: protected routes allow the request.
- `/health` remains public even when auth is enabled.

### Implementation Status

- FOS-007B-impl attaches the existing FOS-007A API key dependency to selected production API routers.
- `/health` remains public.
- Auth disabled keeps default behavior non-breaking.
- Auth enabled protects selected production routes.
- No middleware, rate limiting, webhook signature validation, migrations, or new dependencies are added.
- No secrets are committed to the repo.

### Likely Implementation Files

- `app/main.py`
- `tests/test_api_route_auth.py`
- `docs/security/api-boundary.md`
- `docs/backlog.md`

### Later Test Plan

- `/health` remains public with auth enabled.
- Protected route rejects missing configured key when auth is enabled.
- Protected route rejects missing request key.
- Protected route rejects wrong key.
- Protected route accepts valid key.
- Auth disabled keeps protected routes reachable.
- Error responses do not include configured or provided key values.
- Route wiring uses the existing FOS-007A dependency/helper.

### Security Invariants

- Raw storage and Postgres remain the source of truth.
- Obsidian remains export-only.
- Extracted tasks, risks, and decisions require `evidence_refs`.
- Hallucinated facts must not be persisted.
- LLM pipeline outputs must remain strict JSON and validated before persistence.
- LLMs must not directly mutate production data.
- No secrets are committed to the repo.
- API key comparison remains constant-time through the existing helper.
- Auth fails closed when enabled but the configured key is missing.

## FOS-007C Plan

FOS-007C is split so rate limiting boundaries are planned before implementation:

- FOS-007C-docs-plan: this docs-only ticket.
- FOS-007C-impl-design: choose an edge, reverse proxy, app-layer, shared-state, or combined strategy if needed.
- FOS-007C-impl: implement rate limiting only after explicit approval.

### Scope

- Plan rate limiting boundaries for protected API routes.
- Keep `/health` public and either unthrottled or very lightly protected only by infrastructure in a later ticket.
- Document candidate endpoint categories and suggested limit classes.
- Document implementation questions before coding.
- Change no endpoint behavior in this docs-plan ticket.

### Candidate Route Categories

- Ingestion/write-like routes: `/v1/events`, `/v1/drive/backfill`, `/v1/gmail/backfill`, and `/v1/knowledge/ingest-text`.
- Expensive AI/search/knowledge routes: `/v1/knowledge/score`, `/v1/knowledge/search`, `/v1/knowledge/ask`, and `/v1/knowledge/attention`.
- Extraction routes: `/v1/extraction/*`.
- Public health route: `/health` remains public.

### Suggested Limit Classes

- Ingestion/write-like routes: conservative write-oriented limits to prevent accidental bulk ingestion or repeated backfills.
- Expensive AI/search/knowledge routes: stricter cost-oriented limits, especially for ask, score, and broad search patterns.
- Extraction routes: job-oriented limits that account for document size and downstream processing cost.
- Public health route: no app-layer limit by default; later infrastructure can add a very light health limit if needed.

### Later Implementation Considerations

- Avoid naive per-process production rate limiting unless explicitly accepted as temporary/dev-only.
- Decide whether rate limiting belongs at the edge/reverse proxy, app layer, or both.
- If app-layer limits need shared state, explicitly plan storage and dependency implications before implementation.
- Rate limit keys should be based on authenticated API key identity or trusted client identity, not untrusted headers alone.
- Errors should be generic and must not expose secret material.
- Implementation must not weaken FOS-007A/FOS-007B auth behavior.

### Likely Later Implementation Files

- `app/main.py` or `app/api/*.py` if route-level integration is needed.
- `app/api/rate_limit.py` or equivalent helper if app-layer implementation is approved.
- `tests/test_api_rate_limit.py`
- `docs/security/api-boundary.md`
- `docs/backlog.md`

### Later Focused Test Plan

- `/health` remains public.
- Auth-disabled behavior remains non-breaking unless rate limiting is explicitly enabled.
- Protected routes receive expected rate limit behavior when enabled.
- Limit exceeded returns a generic 429 response.
- Rate limit errors do not expose API keys or secret values.
- Rate limiting does not bypass or duplicate API key auth.
- No direct LLM or production data mutation is introduced by rate limiting.

### Security Invariants

- Raw storage and Postgres remain the source of truth.
- Obsidian remains export-only.
- Extracted tasks, risks, and decisions require `evidence_refs`.
- Hallucinated facts must not be persisted.
- LLM pipeline outputs must remain strict JSON and validated before persistence.
- LLMs must not directly mutate production data.
- No secrets are committed to the repo.
- API auth remains enforced on protected routes from FOS-007B.
- Rate limiting must not become a substitute for auth.

## Non-Goals

- No auth implementation in this ticket.
- No middleware in this ticket.
- No new dependencies in this ticket.
- No provider webhook routes in this ticket.
- No OAuth scope changes in this ticket.
- No endpoint protection in FOS-007A-docs-plan.
- No rate limiting in FOS-007A-docs-plan.
- No webhook signature validation in FOS-007A-docs-plan.
- No migrations in FOS-007A-docs-plan.
- No production data mutation in FOS-007A-docs-plan.
- No route auth implementation in FOS-007B-docs-plan.
- No endpoint behavior changes in FOS-007B-docs-plan.
- No rate limiting implementation in FOS-007C-docs-plan.
- No middleware in FOS-007C-docs-plan.
- No dependency or lockfile changes in FOS-007C-docs-plan.
- No endpoint behavior changes in FOS-007C-docs-plan.
- No migrations or persistence/storage changes in FOS-007C-docs-plan.
- No production data mutation in FOS-007C-docs-plan.
