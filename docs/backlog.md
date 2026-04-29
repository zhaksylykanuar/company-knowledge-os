# Backlog

Small FOS tickets. Keep tickets scoped and update status when work changes behavior.

## Tickets

- FOS-001: Create project operating system docs/control files
  - status: implemented
  - scope: add AGENTS, CLAUDE, and operational docs.

- FOS-002: Replace unstable Python hash() in manual ingestion with SHA-256
  - status: implemented
  - scope: make manual `content_hash` stable across processes.

- FOS-003: Fix document extraction provenance semantics around source_event_id
  - status: implemented
  - scope: avoid storing chunk IDs in fields that imply SourceEvent IDs.

- FOS-004: Align Drive/Gmail event names with source registry contracts
  - status: implemented
  - scope: make emitted event types compatible with registry validation.

- FOS-005: Convert Gmail raw messages into SourceDocument/chunks
  - status: implemented
  - scope: make Gmail content participate in extraction/search pipeline.

- FOS-006: Add or clarify SourceEvent read model / development event projection
  - status: implemented
  - scope: add a generic deterministic SourceEvent read model; defer development-specific projections.

- FOS-006B: Normalize Drive/Gmail backfill events into SourceEvents
  - status: implemented
  - scope: derive SourceEvent rows for valid new Drive/Gmail ingested events.

- FOS-007: Add API auth/rate-limit/signature-validation plan
  - status: implemented
  - scope: define API boundary protections as a security plan.

- FOS-007A-docs-plan: Plan API key/auth config boundary
  - status: implemented
  - scope: document scope, non-goals, files, tests, invariants, and ticket split for auth config.

- FOS-007A-impl: Add API key/auth config and dependency
  - status: implemented
  - scope: add auth-related config and a reusable API key dependency/helper without endpoint enforcement.
  - non-goals: no endpoint protection, middleware, rate limiting, webhook signature validation, migrations, or production data mutation.
  - implementation: adds `api_auth_enabled`, `api_auth_key`, `api_auth_header_name`, and a reusable API key dependency/helper for later route wiring.
  - tests: cover config defaults, disabled auth, missing key, wrong key, valid key, missing configured key fail-closed behavior, generic errors, custom header name, and `/health` remaining public.
  - security: keep raw storage and Postgres as source of truth, Obsidian export-only, no direct LLM production mutation, strict JSON validation for LLM pipeline outputs, no repo secrets, constant-time API key comparison, and fail-closed behavior when auth is enabled but the key is missing.

- FOS-007B-docs-plan: Plan route auth enforcement
  - status: implemented
  - scope: document selected protected routes, public routes, expected behavior, tests, non-goals, and ticket split for route auth enforcement.

- FOS-007B-impl: Enforce auth on protected internal endpoints
  - status: implemented
  - scope: attach the reusable auth dependency to selected internal ingestion, extraction, and knowledge endpoints after explicit approval.
  - protected routes: `/v1/events`, `/v1/drive/backfill`, `/v1/gmail/backfill`, `/v1/knowledge/ingest-text`, `/v1/knowledge/score`, `/v1/knowledge/search`, `/v1/knowledge/ask`, `/v1/knowledge/attention`, and `/v1/extraction/*`.
  - public routes: keep `/health` public.
  - non-goals: no middleware, rate limiting, webhook signature validation, migrations, dependencies, repo secrets, production data mutation, or direct LLM production mutation.
  - behavior: auth disabled preserves current behavior; auth enabled fails closed without a configured key; missing or wrong request keys reject; valid request key allows.
  - implementation: attaches the existing FOS-007A dependency at router include level in `app/main.py`.
  - tests: cover `/health` public with auth enabled, protected route missing configured key, missing request key, wrong key, valid key, auth disabled behavior, generic errors, and use of the existing FOS-007A dependency/helper.

- FOS-007C: Add rate limiting
  - status: planned
  - scope: add endpoint-appropriate request limits.

- FOS-007D: Add webhook signature validation when webhook routes exist
  - status: planned
  - scope: validate provider signatures or secret tokens before webhook persistence.

- FOS-007E: Define write/action approval enforcement
  - status: planned
  - scope: require auth, feature flags, and explicit approval before write actions.

- FOS-008: Improve search beyond simple ILIKE later
  - status: planned
  - scope: evaluate full-text, trigram, or embedding-based retrieval.
