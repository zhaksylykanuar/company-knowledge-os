# API Boundary Security Plan

## Status

- Endpoint-level auth: planned; reusable API key config/dependency is implemented but not enforced
- Rate limiting: planned
- Webhook signature validation: planned
- Write/action approval boundary: planned
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
- FOS-007B-impl: protect selected internal ingestion/extraction/knowledge endpoints after explicit approval.
- FOS-007C: add rate limiting.
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

### Likely Implementation Files

- `app/main.py` if router-level dependencies are applied centrally.
- Individual `app/api/*.py` files if endpoint-level granularity is required.
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
