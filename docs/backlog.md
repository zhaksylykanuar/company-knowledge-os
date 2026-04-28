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

- FOS-007A: Add API key/auth config and dependency
  - status: planned
  - scope: add configuration and reusable auth dependency without broad enforcement.

- FOS-007B: Enforce auth on protected internal endpoints
  - status: planned
  - scope: protect internal ingestion, extraction, and knowledge endpoints.

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
