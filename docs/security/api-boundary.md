# API Boundary Security Plan

## Status

- Endpoint-level auth: planned
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
- FOS-007A: add config flags and API key dependency.
- FOS-007B: protect internal ingestion/extraction/knowledge endpoints.
- FOS-007C: add rate limiting.
- FOS-007D: add webhook signature validation when webhook routes exist.
- FOS-007E: define write/action approval enforcement before any write endpoints.

## Non-Goals

- No auth implementation in this ticket.
- No middleware in this ticket.
- No new dependencies in this ticket.
- No provider webhook routes in this ticket.
- No OAuth scope changes in this ticket.
