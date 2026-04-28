# Threat Model — Company Knowledge & Decision OS

## Assets
OAuth tokens, raw documents, emails, Jira/Git payloads, extracted facts, approvals, audit logs.

## Trust boundaries
External providers -> backend connectors -> event bus -> source of truth -> agent runner -> outputs.

## Main risks
Prompt injection, token leakage, accidental write, duplicate retries, unsupported claims, webhook spoofing.

## Controls
Read-only scopes first, backend-only tokens, raw storage, evidence validation, idempotency, planned webhook signature validation, planned approval enforcement, append-only audit logs.

## API boundary plan
Endpoint-level auth, rate limiting, webhook signature validation, and write/action approval enforcement are planned in `docs/security/api-boundary.md`. Current work defines the policy only; enforcement is not yet implemented.
