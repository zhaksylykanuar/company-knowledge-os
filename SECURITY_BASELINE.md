# Threat Model — Company Knowledge & Decision OS

## Assets
OAuth tokens, raw documents, emails, Jira/Git payloads, extracted facts, approvals, audit logs.

## Trust boundaries
External providers -> backend connectors -> event bus -> source of truth -> agent runner -> outputs.

## Main risks
Prompt injection, token leakage, accidental write, duplicate retries, unsupported claims, webhook spoofing.

## Controls
Read-only scopes first, backend-only tokens, raw storage, evidence validation,
idempotency, selected protected API routes, fail-closed API auth in non-local
environments, server-side revocable session auth for founder login (Argon2id
password hashing, DB-stored session-token hashes, httpOnly first-party cookie,
DB login brute-force throttle), dedicated fail-closed secret-encryption key
outside local, write/action approval guard, planned webhook signature validation
when webhook routes exist, append-only audit logs.

## CI / Supply Chain Baseline

GitHub Actions run least-privilege tokens, SHA-pinned actions, digest-pinned
service containers, tracked-secret scanning, CodeQL, Dependency Review, uv
dependency submission, and OpenSSF Scorecard SARIF upload. Dependency Review
blocks high-or-critical vulnerable runtime, development, or unknown-scope PR
dependency changes. Local-only `.env`, `secrets/`, `raw_storage/`,
`obsidian_vault/`, and `operator_outputs/` paths must not be tracked.

## API boundary status
The boundary contract lives in code: `app/main.py` registers the protected API
routers behind `require_api_key`, and `app/api/auth.py` enforces it. Endpoint-level
auth is implemented for selected protected API routes. A second, coexisting
identity exists for the founder-facing web app: email+password login on
server-side, revocable sessions (`/api/v1/auth/*`, `require_session`), resolved
alongside the operator key by `get_current_actor` (the operator API key is for
server/CI/admin tooling). Auth is fail-closed outside local/dev:
`enforce_fail_closed_auth` aborts startup when a non-local `APP_ENV` runs with
auth disabled or without a configured API key, so a forgotten flag is a loud
startup failure rather than a silent fail-open exposure. Write/action approval
enforcement exists as a guard for future external writes. Login has a DB-backed
brute-force throttle; general rate limiting and webhook signature validation
remain planned because broad public exposure and webhook routes are not in the
current runtime.
