# Runbook: Google Local Manual Backfill

FOS-024 documents a safe local path for future bounded Gmail and Google Drive
manual backfill testing. It is documentation only. It does not connect to
Google, implement OAuth hardening, production token storage, pagination,
incremental sync, webhooks, retry or rate-limit handling, scheduler jobs, or
full production sync.

## Current Status

- Gmail and Google Drive compatibility backfill routes exist as Source Control
  request wrappers. They record redacted requests and are not production sync.
- Live Gmail and Drive connector execution remains default-off/guarded:
  `GOOGLE_GMAIL_BACKFILL_ENABLED=false` and
  `GOOGLE_DRIVE_BACKFILL_ENABLED=false`.
- Real Google credentials are not included in the repo.
- OAuth hardening, production token storage, pagination, incremental sync,
  webhooks, scheduler jobs, and full production sync are not implemented.
- GitHub or `qaztwin`, Jira, Calendar, meeting transcripts, Telegram inbound
  notes, and Telegram Q&A are separate future work.

## Source Of Truth

- Raw storage and Postgres are authoritative.
- Live Google API responses must be persisted as raw records, source events,
  source documents, or chunks before downstream digest, extraction, retrieval,
  or Q&A use.
- Telegram is an interface and delivery channel, not the source of truth.
- Obsidian is export-only.
- ChatGPT and the OpenAI API are not the database or source of truth.

## Secrets And Credentials Safety

- Do not commit real credentials, OAuth refresh tokens, API keys, private email
  addresses, private file names, customer data, or repository secrets.
- Do not edit `.env` as part of tickets. Local `.env` is private and must stay
  ignored.
- Production should use deployment secrets or a secret manager.
- Tokens must not appear in logs, errors, docs examples, test snapshots, digest
  output, returned API payloads, or Telegram messages.
- Use least-privilege Google scopes.
- Rotate credentials immediately if they are leaked or suspected leaked.
- Use placeholders only in docs and examples, such as `YOUR_API_KEY`,
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `GOOGLE_DRIVE_AI_INBOX_FOLDER_ID`, and `YOUR_SAFE_GMAIL_QUERY`.

## Local Preflight

Before any future local manual backfill test:

- Confirm the repo is clean with `git status --short`.
- Start the local backend with `uv run python scripts/start_local.py`; it
  bootstraps the local workspace and runs migrations before serving
  `127.0.0.1:8765`.
- Use `X-FounderOS-API-Key: YOUR_API_KEY` if local API auth is enabled.
- Enable live Gmail or Drive connector execution only for a controlled local
  orchestrator test.
- Keep Gmail query scope narrow and explicit.
- Keep Drive folder scope explicit with `GOOGLE_DRIVE_AI_INBOX_FOLDER_ID`.
- Start with `max_results=1` before testing the default of 10.
- Do not use the broad Gmail query `in:inbox OR in:sent`.
- Do not add or use a sync-all Drive behavior.

## FOS-029 Controlled Local Preflight Checklist

FOS-029 is preflight-only and docs/checklist-only. It is the controlled
readiness step before any real Gmail or Drive manual backfill is attempted.

Do not run these actions during FOS-029:

- Do not use `POST /v1/gmail/backfill` or `POST /v1/drive/backfill` as proof
  of Google readiness; they only create Source Control requests.
- Do not call Google APIs, OAuth flows, Gmail connectors, or Drive connectors.
- Do not start a local app session that points at real Google services.
- Do not treat a recorded request as a completed provider dry run. Provider
  execution happens only through the Source Control orchestrator/adapters.

The only intended endpoint for the first real local readiness check is
`GET /v1/google/backfill/preflight`, and only in a later human-approved local
run after the human confirms local credentials are configured safely. That
preflight endpoint is intended to report local readiness without calling Google
APIs.

For the first later real local preflight, the human must confirm:

- Local credentials are stored outside repo tracking.
- API auth is enabled for the protected local check.
- A narrow Gmail query has been chosen but is not recorded in docs, tickets,
  logs, or chat.
- A Drive folder boundary has been chosen but is not recorded in docs, tickets,
  logs, or chat.
- First later backfill tickets will start with `max_results=1`.
- The git tree is clean before and after the check.

Record only safe preflight fields:

- Pass/fail readiness booleans.
- Blocker code names.
- Bounded result limits and whether those limits are allowed.
- Preflight notes.

Do not record or capture secrets, credential contents, token values, local
credential paths, local token paths, provider IDs, email addresses, subjects,
snippets, Drive filenames, Drive links, private Gmail queries, Drive folder
IDs, or raw source content.

Stop immediately and investigate if any of these happen:

- The git tree is dirty before or after the check.
- API auth is unexpectedly disabled for a protected local check.
- A connector or Google API call happens unexpectedly.
- Any private metadata appears in output.
- Any credential or token file is modified unexpectedly.
- Any secret or local path appears in logs or docs.
- Any backfill route is accidentally called.

## FOS-035 Google Foundation Readiness Lock

This is the final no-real-credentials foundation lock before a human configures
local Google access. It is meant to keep the first real run boring,
observable, and reversible.

Safe before credentials are configured:

- Offline unit and route tests for preflight, auth gates, disabled gates,
  limits, query/folder guardrails, and response redaction.
- Docs-only checks such as `git diff --name-only` and `git diff --check`.
- Review of the preflight implementation and tests.
- No Google API calls, OAuth flows, Gmail/Drive connector construction,
  credential file reads, token file reads, or real backfill requests.

First real step after the human configures local credentials:

- Run only the protected `GET /v1/google/backfill/preflight` endpoint.
- Do not run the Source Control orchestrator yet.
- Do not use a broad Gmail query.
- Do not use sync-all Drive behavior.
- Do not run any persistence-changing backfill.

Before that real preflight, the human must confirm:

- Credentials are stored outside repo tracking.
- Local API auth is enabled for the protected check.
- The API key is not committed, logged, printed, or pasted into tickets.
- A narrow Gmail query is chosen but not recorded in docs, output, tickets, or
  chat.
- A Drive folder boundary is chosen but not recorded in docs, output, tickets,
  or chat.
- The git tree is clean before and after the check.
- No credential or token files are modified unexpectedly. Token file changes
  are expected only if the human intentionally completes local OAuth.

After a successful real preflight:

- The first Gmail Source Control/orchestrator test must be separately
  human-approved, use `max_results=1`, and use only the chosen narrow query.
- The first Drive Source Control/orchestrator test must be separately
  human-approved, use `max_results=1`, and stay inside the chosen folder
  boundary.
- Treat orchestrator `preview_sync` as a possible real Google API call only
  after a first-class live Google adapter is explicitly implemented and wired.
  The current default registry does not wire real Gmail/Drive clients; the
  compatibility HTTP wrappers themselves do not call Google APIs.
- Inspect only redacted API response metadata.
- Never paste private response content into docs, issues, chat, or logs.

Stop immediately if any of these happen:

- API auth is unexpectedly disabled.
- Preflight tries to instantiate Gmail or Drive connectors.
- Any Google API call happens during preflight.
- Any response or log shows secrets, credential paths, provider IDs, email
  addresses, subjects, snippets, Drive filenames, Drive links, private queries,
  folder IDs, or raw source content.
- The git tree becomes dirty unexpectedly.
- A broad Gmail query is used.
- The Drive folder boundary is missing.
- `max_results` is greater than 1 for the first real backfill test.

## Guardrail Preflight

Before any real Google backfill request, use the protected preflight endpoint to
validate local guardrail readiness without calling Google APIs:

```bash
curl -G http://127.0.0.1:8765/v1/google/backfill/preflight \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "gmail_query=YOUR_SAFE_GMAIL_QUERY" \
  --data-urlencode "gmail_max_results=1" \
  --data-urlencode "drive_max_results=1"
```

`GET /v1/google/backfill/preflight` reports safe readiness booleans, blocker
codes, bounded result limits, whether Gmail/Drive are enabled, and safe local
Google credential file presence. It checks only whether configured client
secret and token file paths are non-blank and whether those files are present;
it does not read file contents or validate credential JSON. Missing Gmail or
Drive token files are reported separately because the current local connector
can create token files during a future manual OAuth flow.

The preflight does not call Gmail, Drive, OAuth, or connector code. It does not
echo credential paths, token paths, the Gmail query, Drive folder ID,
credentials, private emails, or private file names. File presence does not
prove credential validity, token freshness, token refresh support, production
OAuth hardening, or production token storage. `overall_ready` is true only when
Gmail guardrails, Drive guardrails, and the local credential file presence
checks are ready for a bounded manual backfill check.

## Preferred Source Control Request Flow

Use this path for operator runs. It records a request and lets the Source
Control orchestrator own provider execution, receipts, state transitions, and
sanitized summaries.

Gmail preview/backfill request:

```bash
curl -X POST http://127.0.0.1:8765/v1/founder/sources/gmail/backfill \
  -H "Content-Type: application/json" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  -d '{
    "request_key": "gmail-backfill-manual-YYYYMMDD",
    "requested_by": "operator",
    "input": {
      "max_results": 1,
      "mode": "preview_first"
    }
  }'
```

Drive preview/backfill request:

```bash
curl -X POST http://127.0.0.1:8765/v1/founder/sources/drive/backfill \
  -H "Content-Type: application/json" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  -d '{
    "request_key": "drive-backfill-manual-YYYYMMDD",
    "requested_by": "operator",
    "input": {
      "max_results": 1,
      "mode": "preview_first"
    }
  }'
```

Then run queued requests:

```bash
uv run python scripts/run_source_requests.py --confirm-run "RUN SOURCE REQUESTS" --limit 5
```

This advances the Source Control request lifecycle. In the current default
registry it does not execute real Gmail/Drive API reads because real Google
clients are not wired.

Report only request IDs, run IDs, statuses, counts, watermarks, and sanitized
blocker classes. Do not paste provider content, private queries, folder IDs, or
credential paths into reports.

## Compatibility Gmail Backfill Request Wrapper

This route remains for compatibility. It is already a Source Control wrapper:
it records a redacted request and does not call Gmail, write raw storage, or
persist provider data. Prefer the `/v1/founder/sources/gmail/{action}` route
for new operator flows.

Endpoint:

- Method and path: `POST /v1/gmail/backfill`
- Query parameters:
  - `query`: explicit Gmail search query. If omitted, the route can use the
    configured query path, but it records only a boolean flag and never returns
    or stores the query value.
  - `max_results`: optional bounded result count. Default is 10. Hard maximum
    is 50.
  - `persist`: optional boolean. Defaults to `false`; `false` records a
    `preview_sync` request and `true` records a `backfill` request.
  - `request_key`: optional idempotency key for the recorded Source Control
    request.

Activation and guardrails:

- Blank explicit queries are rejected.
- The historical broad explicit query `in:inbox OR in:sent` is rejected.
- `max_results=0`, negative values, and values above 50 are rejected before a
  request is recorded.
- Live-provider and production-operation acknowledgements are reduced to
  booleans in the recorded request; acknowledgement text is not stored or
  returned.
- The API response is intentionally redacted. It returns request IDs, status,
  source/action type, safe limits, and sanitized input flags only.

Compatibility preview request:

```bash
curl -X POST "http://127.0.0.1:8765/v1/gmail/backfill?persist=false&query=YOUR_SAFE_GMAIL_QUERY&max_results=1&request_key=gmail-preview-YYYYMMDD" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

Compatibility backfill request:

```bash
curl -X POST "http://127.0.0.1:8765/v1/gmail/backfill?persist=true&query=YOUR_SAFE_GMAIL_QUERY&max_results=1&request_key=gmail-backfill-YYYYMMDD" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

## Compatibility Google Drive Backfill Request Wrapper

This route remains for compatibility. It is already a Source Control wrapper:
it records a redacted request and does not call Drive, write raw storage, or
persist provider data. Prefer the `/v1/founder/sources/drive/{action}` route
for new operator flows.

Endpoint:

- Method and path: `POST /v1/drive/backfill`
- Query parameters:
  - `max_results`: optional bounded result count. Default is 10. Hard maximum
    is 50.
  - `persist`: optional boolean. Defaults to `false`; `false` records a
    `preview_sync` request and `true` records a `backfill` request.
  - `request_key`: optional idempotency key for the recorded Source Control
    request.

Activation and guardrails:

- The route records only whether a Drive folder boundary is configured. It does
  not store or return the folder ID.
- Drive backfill execution must remain bounded to the configured folder when a
  live orchestrator adapter is used.
- Sync-all Drive behavior is not allowed.
- `max_results=0`, negative values, and values above 50 are rejected before a
  request is recorded.
- Live-provider and production-operation acknowledgements are reduced to
  booleans in the recorded request; acknowledgement text is not stored or
  returned.
- The API response is intentionally redacted. It returns request IDs, status,
  source/action type, safe limits, and sanitized input flags only.

Compatibility preview request:

```bash
curl -X POST "http://127.0.0.1:8765/v1/drive/backfill?persist=false&max_results=1&request_key=drive-preview-YYYYMMDD" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

Compatibility backfill request:

```bash
curl -X POST "http://127.0.0.1:8765/v1/drive/backfill?persist=true&max_results=1&request_key=drive-backfill-YYYYMMDD" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

## Verification After Backfill

Use stored source activity checks after a bounded manual backfill. These
endpoints read stored `SourceEvent` rows and do not infer decisions, tasks, or
risks.

JSON source activity digest:

```bash
curl -G http://127.0.0.1:8765/v1/digest/source-activity \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "start_at=2026-01-01T00:00:00+00:00" \
  --data-urlencode "end_at=2026-01-02T00:00:00+00:00" \
  --data-urlencode "limit=10"
```

Plain-text source activity digest:

```bash
curl -G http://127.0.0.1:8765/v1/digest/source-activity/text \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "start_at=2026-01-01T00:00:00+00:00" \
  --data-urlencode "end_at=2026-01-02T00:00:00+00:00" \
  --data-urlencode "limit=10"
```

Check that:

- The selected window is explicit and timezone-aware.
- Source activity appears only for the expected bounded manual test.
- If the selected local window also contains unrelated source systems, use the
  local normalization and triage script `--source` filter, for example
  `--source gmail --source drive`, so preview and write commands operate on the
  same bounded source subset.
- Manual backfill responses use safe counts/status fields; verify detailed
  stored activity through `SourceEvent` and digest checks instead of response
  metadata.
- Entries include evidence refs or equivalent source pointers.
- Responses do not expose raw full email bodies or raw full document contents.
- Digest output is source activity only and does not infer decisions, tasks, or
  risks.

## Stop Conditions

Stop the manual test and investigate before proceeding if any of these happen:

- Result count is broader than expected.
- Evidence refs or source pointers are missing.
- Raw full email body content or raw full document content appears in API
  responses.
- Credentials appear in logs, errors, docs examples, test snapshots, returned
  API payloads, or Telegram messages.
- Connector or network paths are called while the integration is disabled.
- `.env` or secret files are accidentally modified.
- Source events or digest output do not show the expected bounded activity.

## Next Production Gaps

- OAuth hardening.
- Production token storage policy.
- Pagination and incremental sync.
- Retry and rate-limit handling.
- Failure visibility and audit trail.
- Scheduler and daily jobs.
- Production source allowlist policy.
- Human review and evidence validation for extracted items.
