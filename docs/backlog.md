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

- FOS-007C-docs-plan: Plan rate limiting boundary
  - status: implemented
  - scope: document rate limiting boundaries for protected API routes without behavior changes.
  - candidate categories: ingestion/write-like routes (`/v1/events`, `/v1/drive/backfill`, `/v1/gmail/backfill`, `/v1/knowledge/ingest-text`), expensive AI/search/knowledge routes (`/v1/knowledge/score`, `/v1/knowledge/search`, `/v1/knowledge/ask`, `/v1/knowledge/attention`), extraction routes (`/v1/extraction/*`), and public health (`/health`).
  - non-goals: no implementation, middleware, dependency or lockfile changes, endpoint behavior changes, migrations, persistence/storage changes, production data mutation, repo secrets, or direct LLM production mutation.
  - implementation questions: choose edge, reverse proxy, app-layer, or combined limits before coding; avoid naive per-process production limits unless explicitly accepted as temporary/dev-only; plan shared-state or dependency implications before implementation.
  - security: rate limit keys should be based on authenticated API key identity or trusted client identity, not untrusted headers alone; errors must be generic and must not expose secret material; rate limiting must not weaken or replace FOS-007A/FOS-007B auth.

- FOS-007C-impl-design: Choose rate limiting implementation strategy
  - status: planned
  - scope: decide edge/app/shared-state strategy, config surface, storage implications, and focused test strategy before implementation.

- FOS-007C-impl: Add rate limiting
  - status: planned
  - scope: implement endpoint-appropriate request limits only after explicit approval.

- FOS-007D: Add webhook signature validation when webhook routes exist
  - status: planned
  - scope: validate provider signatures or secret tokens before webhook persistence.

- FOS-007E: Define write/action approval enforcement
  - status: planned
  - scope: require auth, feature flags, and explicit approval before write actions.

- FOS-008: Improve search beyond simple ILIKE later
  - status: planned
  - scope: evaluate full-text, trigram, or embedding-based retrieval.

- FOS-009: Add one-step manual knowledge processing endpoint
  - status: implemented
  - scope: add `POST /v1/knowledge/ingest-text-process` for MVP manual text processing.
  - implementation: reuses existing manual ingestion, deterministic extraction, and score processing for the new document.
  - behavior: returns document/raw refs, chunk count, extraction counts, score counts, evidence summary, and next-step endpoint hints.
  - non-goals: no existing endpoint behavior changes, LLM behavior changes, new LLM calls, dependencies, migrations, middleware, rate limiting, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: endpoint is under the existing protected knowledge router; `/health` remains public; extracted tasks/risks/decisions still require `evidence_refs`.

- FOS-010: Add evidence preview to one-step knowledge processing
  - status: implemented
  - scope: return a small `extracted_items_preview` from `POST /v1/knowledge/ingest-text-process`.
  - behavior: preview includes persisted tasks, risks, and decisions with `evidence_refs`, source document/chunk IDs, short evidence snippets from stored evidence quotes, and existing score metadata when available.
  - non-goals: no existing endpoint behavior changes, LLM behavior changes, new LLM calls, fabricated facts/evidence, dependencies, migrations, middleware, rate limiting, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: preview skips any extracted entity without `evidence_refs`; the endpoint remains protected by existing API auth.

- FOS-011: Add MVP manual knowledge quickstart
  - status: implemented
  - scope: add a small docs-only quickstart for the current FOS-009/FOS-010 manual knowledge flow.
  - behavior: documents local prerequisites, the one-step manual processing endpoint, evidence-backed preview fields, follow-up search/ask/attention/export checks, troubleshooting, and safety notes.
  - non-goals: no code, tests, endpoint behavior changes, LLM behavior changes, dependencies, migrations, middleware, rate limiting, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: examples use placeholders only and reinforce raw storage plus Postgres as source of truth, Obsidian export-only behavior, and evidence-backed extraction invariants.

- FOS-012: Add Telegram digest product contract
  - status: implemented
  - scope: add a docs-only future product and architecture contract for Telegram as an interface and daily digest delivery mechanism.
  - behavior: documents planned source inputs, source-of-truth boundaries, daily digest flow, Telegram Q&A flow, digest sections, safety/privacy requirements, and current implemented versus planned status.
  - non-goals: no Telegram implementation, digest implementation, connector implementation, code, tests, dependencies, migrations, middleware, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: reinforces raw storage plus Postgres as source of truth, Obsidian export-only behavior, strict JSON validation, evidence-backed extraction, no direct LLM production mutation, and placeholder-only examples.

- FOS-013: Add source activity digest builder
  - status: implemented
  - scope: add a small deterministic internal digest builder for stored `SourceEvent` activity in an explicit timezone-aware time window.
  - behavior: returns the requested window, source/event/object-type counts, traceable source activity entries, and evidence refs without raw body text or inferred tasks/risks/decisions.
  - non-goals: no Telegram implementation, scheduler, connector implementation, LLM calls, LLM summarization, task/risk/decision inference, dependencies, migrations, middleware, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: reads persisted source activity only, requires explicit aware datetimes, keeps raw storage plus Postgres as source of truth, includes evidence pointers, and does not call OpenAI/ChatGPT.

- FOS-014: Expose source activity digest endpoint
  - status: implemented
  - scope: add a small protected `GET /v1/digest/source-activity` API endpoint around the FOS-013 deterministic digest builder.
  - behavior: accepts explicit timezone-aware `start_at` and `end_at` query params plus a bounded `limit`, returns the requested window, source/event/object-type counts, traceable source activity entries, and evidence refs.
  - non-goals: no Telegram implementation, scheduler, connector implementation, LLM calls, LLM summarization, task/risk/decision inference, dependencies, migrations, middleware, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: uses the existing protected API auth boundary, reads persisted `SourceEvent` data only, rejects naive or inverted windows, omits raw source bodies, and does not call OpenAI/ChatGPT.

- FOS-015: Add digest API manual quickstart
  - status: implemented
  - scope: add docs-only manual verification guidance for `GET /v1/digest/source-activity`.
  - behavior: documents protected endpoint usage, timezone-aware `start_at` and `end_at`, bounded `limit`, response fields, empty digest behavior, and troubleshooting for auth and window validation.
  - non-goals: no code, tests, Telegram implementation, scheduler, connector implementation, LLM calls, LLM summarization, task/risk/decision inference, dependencies, migrations, middleware, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: examples use placeholders only and reinforce that the endpoint reads stored `SourceEvent` data without raw body output, LLM calls, Telegram delivery, or inferred digest claims.

- FOS-016: Render source activity digest text
  - status: implemented
  - scope: add a deterministic non-LLM text renderer for existing source activity digest output.
  - behavior: formats the digest title, explicit window, counts, limited source activity entries, truncation metadata, evidence refs, and empty-state message as plain text.
  - non-goals: no Telegram implementation, scheduler, connector implementation, LLM calls, LLM summarization, task/risk/decision/commitment/recommendation inference, API behavior changes, dependencies, migrations, middleware, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: renderer uses the provided digest dict only, avoids DB/API/LLM access, whitelists rendered evidence ref fields, omits raw body-like fields, and labels output as source activity only.

- FOS-017: Expose source activity digest text endpoint
  - status: implemented
  - scope: add a protected `GET /v1/digest/source-activity/text` endpoint around the FOS-013 digest builder and FOS-016 text renderer.
  - behavior: accepts explicit timezone-aware `start_at` and `end_at` query params plus a bounded `limit`, returns deterministic `text/plain` source activity digest output, and preserves the existing JSON digest endpoint behavior.
  - non-goals: no Telegram implementation, scheduler, connector implementation, LLM calls, LLM summarization, task/risk/decision/commitment/recommendation inference, dependencies, migrations, middleware, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: uses the existing protected API auth boundary, reads persisted `SourceEvent` data only through the digest builder, rejects naive or inverted windows, omits raw source bodies, and does not call OpenAI/ChatGPT.

- FOS-018: Add Telegram delivery adapter
  - status: implemented
  - scope: add a small outbound Telegram `sendMessage` adapter for already-rendered plain digest text.
  - behavior: validates non-empty token, chat ID, and text; splits long text into ordered Telegram-safe chunks; builds plain payloads without `parse_mode`; sends chunks through an injected transport; and returns safe delivery status, counts, message IDs, and failure summary.
  - non-goals: no Telegram webhook, polling, inbound Q&A, scheduler, connector implementation, digest building, LLM calls, LLM summarization, task/risk/decision/commitment/recommendation inference, dependencies, migrations, API routes, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: keeps bot tokens out of result/error summaries, uses placeholders in tests/docs only, makes tests use fake transports, and does not store Telegram delivery results in the database.

- FOS-019: Add source integration credentials contract
  - status: implemented
  - scope: add a docs/config-contract for future real source connectivity before connecting external services.
  - behavior: documents current source readiness, source-of-truth rules, stable source identity fields, credential and secret handling expectations, per-source credential categories, activation/allowlist rules, webhook/sync safety, evidence requirements, and recommended connection order.
  - non-goals: no code, tests, real connector implementation, OAuth flow, webhook, scheduler, Telegram inbound bot/Q&A, external API calls, runtime behavior changes, dependencies, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: reinforces that `.env` stays ignored and local, production secrets belong in a secret manager or deployment secret store, provider scopes should be least-privilege and allowlisted, tokens must not appear in logs/errors/docs/tests/Telegram messages, and extraction/digest/Q&A must run from stored evidence-backed data.

- FOS-021: Add Google integration activation guardrails
  - status: implemented
  - scope: make existing Gmail and Google Drive backfill routes default-off and add minimal scope guardrails before real credentials are used.
  - behavior: adds default-disabled Gmail and Drive backfill settings; Gmail backfill rejects missing, blank, or historical broad `in:inbox OR in:sent` queries before connector calls; Drive backfill rejects disabled use and missing folder boundary before connector calls.
  - non-goals: no real Google API calls in tests, OAuth implementation, webhook, scheduler, pagination, incremental sync, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, dependencies, migrations, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: keeps Google access read-only first, prevents accidental broad Gmail sync, keeps Drive bounded to the configured AI inbox folder, uses safe default-off `.env.example` placeholders, and preserves existing route auth.

- FOS-022: Harden Gmail backfill limits
  - status: implemented
  - scope: make the existing manual Gmail backfill path more bounded before real user Gmail credentials are connected.
  - behavior: keeps Gmail backfill default-off and query-gated; uses a default limit of 10 messages and a hard maximum of 50 messages; rejects zero, negative, or too-large limits before connector calls; and keeps raw full message body content out of API responses.
  - non-goals: no real Gmail connection, OAuth implementation, webhook, scheduler, pagination, incremental sync, Google Drive changes, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, dependencies, migrations, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: requires a narrow explicit or configured query, blocks the historical broad `in:inbox OR in:sent` query, passes only bounded limits to the connector path, and preserves raw storage plus Postgres as source of truth.

- FOS-023: Harden Drive backfill limits
  - status: implemented
  - scope: make the existing manual Google Drive backfill path more bounded before real user Drive credentials are connected.
  - behavior: keeps Drive backfill default-off and folder-gated; uses a default limit of 10 files and a hard maximum of 50 files; rejects zero, negative, too-large limits, or blank folder boundaries before connector calls; and keeps raw full document content out of API responses.
  - non-goals: no real Drive connection, OAuth implementation, webhook, scheduler, pagination, incremental sync, Gmail changes, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, dependencies, migrations, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: keeps Drive bounded to the configured AI inbox folder, passes only bounded limits to the connector path, and preserves raw storage plus Postgres as source of truth.

- FOS-024: Add Google local backfill runbook
  - status: implemented
  - scope: add docs-only local credentials and safe manual backfill guidance for Gmail and Google Drive.
  - behavior: documents current default-off guardrails, Gmail explicit safe query requirements, blocked broad Gmail query, Drive folder boundary, bounded `max_results`, placeholder curl examples, post-backfill digest verification, stop conditions, and remaining production gaps.
  - non-goals: no code, tests, runtime behavior changes, real Google calls, OAuth implementation, credential storage, webhooks, scheduler, production sync, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: reinforces that `.env` stays local and ignored, real credentials must not be committed or logged, raw storage plus Postgres remain source of truth, and API responses must not expose raw full email bodies or raw full document contents.

- FOS-025: Add Google backfill preflight endpoint
  - status: implemented
  - scope: add a protected local readiness endpoint for Gmail and Google Drive manual backfill guardrails.
  - behavior: `GET /v1/google/backfill/preflight` reports safe readiness booleans, bounded result limits, blocker codes, and preflight notes for Gmail and Drive without calling Google APIs or connector paths.
  - non-goals: no real Gmail/Drive connection, OAuth implementation, credential storage, webhooks, scheduler, production sync, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, dependencies, migrations, repo secrets, production data mutation, Gmail/Drive sync behavior changes, or Obsidian/raw storage manual edits.
  - security: keeps Gmail query values, Drive folder IDs, token paths, credentials, private emails, and private file names out of responses, errors, docs examples, and tests.

- FOS-027: Add Google credential preflight checks
  - status: implemented
  - scope: extend the protected Google manual backfill preflight endpoint with safe local Google credential file presence checks.
  - behavior: reports whether the configured Google client secrets path, Gmail token path, and Drive token path are non-blank and whether the corresponding files are present, without reading file contents or validating credential JSON.
  - non-goals: no real Gmail/Drive connection, Google API calls, OAuth flow, credential storage, token refresh, production OAuth hardening, webhooks, scheduler, production sync, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, dependencies, migrations, repo secrets, production data mutation, Gmail/Drive sync behavior changes, or Obsidian/raw storage manual edits.
  - security: does not return credential paths, token paths, credential values, token values, Gmail query values, Drive folder IDs, private emails, or private file names; file presence is documented as local preflight only and not proof of credential validity.

- FOS-028: Redact Google backfill response metadata
  - status: implemented
  - scope: make existing Gmail and Google Drive manual backfill API responses safe before first controlled real Google backfill.
  - behavior: keeps persistence and processing behavior unchanged, but returns redacted counts/status fields instead of raw event payloads, snippets, subjects, email addresses, attachment names, file names, Drive links, provider object IDs, document previews, or external metadata.
  - non-goals: no real Gmail/Drive connection, Google API calls, OAuth flow, credential storage, token refresh, production OAuth hardening, webhooks, scheduler, production sync, GitHub/Jira/Calendar/Telegram inbound implementation, LLM calls, dependencies, migrations, repo secrets, production data mutation, Gmail/Drive sync broadening, or Obsidian/raw storage manual edits.
  - security: manual backfill verification should use safe counts/status plus stored `SourceEvent` and digest checks; responses must not expose raw source content or sensitive provider metadata.

- FOS-029: Controlled local Google preflight checklist
  - status: implemented
  - scope: add a docs-only checklist for the first controlled local Google preflight readiness step before any real Gmail or Drive backfill is attempted.
  - behavior: documents that FOS-029 is preflight-only, forbids Gmail and Drive backfill route calls, explains that `persist=false` can still call connector paths, identifies `GET /v1/google/backfill/preflight` as the only intended endpoint for a later human-approved local readiness check, and limits recorded results to readiness booleans, blocker codes, bounded limits, and notes.
  - non-goals: no code, tests, real credentials, credential file reads, token file reads, Google API calls, OAuth flow, local app startup against real services, Gmail backfill, Drive backfill, connector calls, production sync, dependencies, migrations, repo secrets, production data mutation, or Obsidian/raw storage manual edits.
  - security: forbids recording secrets, credential contents, token values, local credential paths, local token paths, provider IDs, email addresses, subjects, snippets, Drive filenames, Drive links, private Gmail queries, Drive folder IDs, or raw source content; requires local credentials to stay outside repo tracking and API auth to be enabled before a later protected local check.
