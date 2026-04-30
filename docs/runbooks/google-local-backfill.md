# Runbook: Google Local Manual Backfill

FOS-024 documents a safe local path for future bounded Gmail and Google Drive
manual backfill testing. It is documentation only. It does not connect to
Google, implement OAuth hardening, production token storage, pagination,
incremental sync, webhooks, retry or rate-limit handling, scheduler jobs, or
full production sync.

## Current Status

- Gmail and Google Drive manual backfill routes exist, but they are guarded and
  are not production sync.
- Gmail and Drive backfill are default-off:
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
- Start Postgres and Redis with `docker compose up -d postgres redis`.
- Apply migrations with `uv run alembic upgrade head`.
- Start the API with `uv run uvicorn app.main:app --reload`.
- Use `X-FounderOS-API-Key: YOUR_API_KEY` if local API auth is enabled.
- Enable Gmail or Drive backfill only for a controlled local test.
- Keep Gmail query scope narrow and explicit.
- Keep Drive folder scope explicit with `GOOGLE_DRIVE_AI_INBOX_FOLDER_ID`.
- Start with `max_results=1` before testing the default of 10.
- Do not use the broad Gmail query `in:inbox OR in:sent`.
- Do not add or use a sync-all Drive behavior.

## Guardrail Preflight

Before calling either manual backfill route, use the protected preflight endpoint
to validate local guardrail readiness without calling Google APIs:

```bash
curl -G http://localhost:8000/v1/google/backfill/preflight \
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

## Gmail Safe Manual Backfill

Endpoint:

- Method and path: `POST /v1/gmail/backfill`
- Query parameters:
  - `query`: explicit Gmail search query. If omitted, the route can use the
    configured `GOOGLE_GMAIL_BACKFILL_QUERY` only when it is non-blank and safe.
  - `max_results`: optional bounded result count. Default is 10. Hard maximum
    is 50.
  - `persist`: optional boolean. Defaults to `true`.

Activation and guardrails:

- `GOOGLE_GMAIL_BACKFILL_ENABLED` must be explicitly enabled locally.
- `GOOGLE_GMAIL_BACKFILL_QUERY` is optional and must be narrow if used.
- Blank queries are rejected.
- The historical broad query `in:inbox OR in:sent` is rejected.
- `max_results=0`, negative values, and values above 50 are rejected before the
  connector path.
- The API response is intentionally redacted. It returns safe counts/status
  fields only and must not include raw full email body content, snippets,
  subjects, email addresses, attachment names, provider message IDs, or thread
  IDs.

Start with a dry manual check before persistence:

```bash
curl -X POST "http://localhost:8000/v1/gmail/backfill?persist=false&query=YOUR_SAFE_GMAIL_QUERY&max_results=1" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

After confirming the query and result bounds are safe, a local operator can use
the same narrow query with `persist=true`:

```bash
curl -X POST "http://localhost:8000/v1/gmail/backfill?persist=true&query=YOUR_SAFE_GMAIL_QUERY&max_results=1" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

## Google Drive Safe Manual Backfill

Endpoint:

- Method and path: `POST /v1/drive/backfill`
- Query parameters:
  - `max_results`: optional bounded result count. Default is 10. Hard maximum
    is 50.
  - `persist`: optional boolean. Defaults to `true`.

Activation and guardrails:

- `GOOGLE_DRIVE_BACKFILL_ENABLED` must be explicitly enabled locally.
- `GOOGLE_DRIVE_AI_INBOX_FOLDER_ID` must be configured and non-blank.
- Drive backfill must remain bounded to that configured folder.
- Sync-all Drive behavior is not allowed.
- `max_results=0`, negative values, and values above 50 are rejected before the
  connector path.
- The API response is intentionally redacted. It returns safe counts/status
  fields only and must not include raw full document contents, file names,
  titles, Drive links, provider file IDs, or large source contents.

Start with a dry manual check before persistence:

```bash
curl -X POST "http://localhost:8000/v1/drive/backfill?persist=false&max_results=1" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

After confirming the folder boundary and result bounds are safe, a local
operator can use the same bounded folder with `persist=true`:

```bash
curl -X POST "http://localhost:8000/v1/drive/backfill?persist=true&max_results=1" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

## Verification After Backfill

Use stored source activity checks after a bounded manual backfill. These
endpoints read stored `SourceEvent` rows and do not infer decisions, tasks, or
risks.

JSON source activity digest:

```bash
curl -G http://localhost:8000/v1/digest/source-activity \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "start_at=2026-01-01T00:00:00+00:00" \
  --data-urlencode "end_at=2026-01-02T00:00:00+00:00" \
  --data-urlencode "limit=10"
```

Plain-text source activity digest:

```bash
curl -G http://localhost:8000/v1/digest/source-activity/text \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "start_at=2026-01-01T00:00:00+00:00" \
  --data-urlencode "end_at=2026-01-02T00:00:00+00:00" \
  --data-urlencode "limit=10"
```

Check that:

- The selected window is explicit and timezone-aware.
- Source activity appears only for the expected bounded manual test.
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
