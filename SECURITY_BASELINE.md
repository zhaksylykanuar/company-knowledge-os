# Threat Model — Company Knowledge & Decision OS

## Assets
OAuth tokens, raw documents, emails, Jira/Git payloads, extracted facts, approvals, audit logs.

## Trust boundaries
External providers -> backend connectors -> event bus -> source of truth -> agent runner -> outputs.

## Main risks
Prompt injection, token leakage, accidental write, duplicate retries, unsupported claims, webhook spoofing.

## Controls
Read-only scopes first, backend-only tokens, raw storage, evidence validation, idempotency, webhook signature validation, Telegram approval, append-only audit logs.