# MVP Manual Knowledge Quickstart

This quickstart shows the current manual MVP loop:

```text
manual note
-> raw storage + Postgres
-> deterministic extraction
-> deterministic scoring
-> evidence-backed preview, search, ask, attention, or Obsidian export
```

Use this flow when you want to paste a small piece of safe company text into
FounderOS and immediately inspect extracted tasks, risks, decisions, and their
supporting evidence.

## Manual Pilot Dry Run

Before a 5-day manual pilot, run the provider-free synthetic readiness check:

```bash
.venv/bin/python scripts/pilot_dry_run.py --format json
.venv/bin/python scripts/pilot_dry_run.py --format text
```

The command exercises the current MVP contracts with synthetic sample data only:

- attention confidence policy, including low/medium confidence hidden items
  moving to visible `review_optional`;
- target digest section shape, with hidden low-priority output as counts only;
- GitHub, Jira, and Drive activity normalization;
- meeting transcript draft artifacts for summary, decisions, actions, risks,
  questions, Jira draft tickets, and KB update drafts;
- feedback context shape suitable for later `AttentionContext.recent_feedback`.

It does not read `.env` files, inspect local private data, open DB sessions,
call providers or source APIs, run ingestion, run migrations, write files,
create Jira issues, send Telegram/Slack messages, or write KB/Obsidian output.
Use it as the first pilot readiness check, then follow
`docs/runbooks/manual-pilot.md` for the day-by-day manual pilot checklist.

## Prerequisites

- Python 3.12 or newer.
- Project dependencies available through `uv`.
- Postgres and Redis from the repo `docker-compose.yml`.
- Database migrations applied before DB-backed endpoints are used.
- API auth configured only if your local environment enables it.

Start local services:

```bash
docker compose up -d postgres redis
uv run alembic upgrade head
```

Start the API:

```bash
uv run uvicorn app.main:app --reload
```

Check that the API is reachable:

```bash
curl http://localhost:8000/health
```

## Process Manual Text

`POST /v1/knowledge/ingest-text-process` is the MVP one-step endpoint. It
ingests manual text, stores raw input, creates document chunks, runs deterministic
extraction, refreshes deterministic scores for the new document, and returns a
compact processing summary.

If API auth is disabled, omit the `X-FounderOS-API-Key` header. If auth is
enabled, use a real key from your own environment; never paste real secrets into
docs, commits, tickets, or sample text.

```bash
curl -X POST http://localhost:8000/v1/knowledge/ingest-text-process \
  -H "Content-Type: application/json" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  -d '{
    "title": "Example customer follow-up note",
    "text": "Client ExampleCo needs follow up. TODO send proposal by next week. Risk: the client is worried about security access. Decision: start with read-only data collection.",
    "source_type": "manual",
    "project_key": "example-project",
    "client_key": "example-client",
    "people": ["example-person"],
    "tags": ["manual", "mvp"]
  }'
```

The request fields are:

- `title`: required, non-empty, max 300 characters.
- `text`: required, non-empty.
- `source_type`: optional, defaults to `manual`.
- `project_key`: optional string or `null`.
- `client_key`: optional string or `null`.
- `people`: optional list of strings.
- `tags`: optional list of strings.

## Response Fields

The response keeps the existing one-step processing fields and adds the
FOS-010 preview:

- `processed`: `true` when the one-step flow completed.
- `document_id`: the new source document ID.
- `raw_ref`: the raw manual content reference.
- `chunks_created`: number of chunks created from the submitted text.
- `extraction_counts`: task, risk, decision, and total counts.
- `score_counts`: created, updated, task, risk, decision, and total score counts.
- `evidence_summary`: extracted entity count, whether all extracted entities have
  `evidence_refs`, source chunk IDs, and sample evidence refs.
- `extracted_items_preview`: compact preview of persisted extracted items.
- `next_steps`: endpoint or command hints for search, ask, attention, and export.

Each `extracted_items_preview` item is built from persisted extracted tasks,
risks, and decisions. Preview items without usable `evidence_refs` are skipped.
When present, each preview item includes:

- `kind`: `task`, `risk`, or `decision`.
- `id`, `title`, `source_document_id`, and `chunk_id`.
- `evidence_refs`: supporting evidence references from stored extraction data.
- `evidence_snippet`: a shortened snippet from an existing stored evidence quote,
  or `null` if no quote is available.
- `score`: deterministic score metadata when an existing score is available.
- `metadata`: type-specific fields such as task status, risk severity, decision
  text, owner, due date, and confidence.

The preview must not be treated as new source data. Raw storage and Postgres are
the source of truth.

## Next Manual Checks

After processing, use the returned `document_id`, preview titles, or text terms
to inspect the stored knowledge through existing read endpoints.

Search:

```bash
curl "http://localhost:8000/v1/knowledge/search?q=proposal&limit=10" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

Ask:

```bash
curl -X POST http://localhost:8000/v1/knowledge/ask \
  -H "Content-Type: application/json" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  -d '{
    "question": "What tasks were extracted from the latest customer note?",
    "limit": 10
  }'
```

Attention:

```bash
curl "http://localhost:8000/v1/knowledge/attention?limit=10" \
  -H "X-FounderOS-API-Key: YOUR_API_KEY"
```

Source activity digest:

```bash
curl -G http://localhost:8000/v1/digest/source-activity \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "start_at=2026-01-01T00:00:00+00:00" \
  --data-urlencode "end_at=2026-01-02T00:00:00+00:00" \
  --data-urlencode "limit=20"
```

`GET /v1/digest/source-activity` is a protected manual check for stored source
activity. It reads existing `SourceEvent` rows only and requires explicit ISO
datetimes with timezone in `start_at` and `end_at`. The optional `limit` is
bounded by the API.

The digest response includes:

- `digest_type`: `source_activity`.
- `window`: the requested `start_at` and `end_at`.
- `counts`: total count plus counts by source system, event type, and source
  object type.
- `entries`: limited source activity entries with source identifiers, event
  time, title, source URL when available, short evidence text, and debug-only
  `evidence_refs` when `debug_evidence=true`.
- `metadata`: entry limit, returned entry count, truncation flag, source model,
  generated time, debug evidence flag, duplicate-collapse metadata, and
  `llm_used`.

An empty window is valid and returns an empty digest. The endpoint does not call
an LLM, generate a human-written summary, infer decisions, tasks, risks,
commitments, or recommendations, send anything to Telegram, or implement a daily
scheduler. It does not expose raw full email bodies, raw transcript text,
secrets, or large source contents.

Rendered source activity digest text:

```bash
curl -G http://localhost:8000/v1/digest/source-activity/text \
  -H "X-FounderOS-API-Key: YOUR_API_KEY" \
  --data-urlencode "start_at=2026-01-01T00:00:00+00:00" \
  --data-urlencode "end_at=2026-01-02T00:00:00+00:00" \
  --data-urlencode "limit=20"
```

`GET /v1/digest/source-activity/text` is the protected plain-text rendering of
the same deterministic source activity digest. It uses the same timezone-aware
window validation and bounded `limit` as the JSON endpoint, calls the existing
non-LLM renderer, and returns `text/plain`. The text is source activity only: it
does not add a human-written summary, infer decisions, tasks, or risks, send
anything to Telegram, or expose raw full source bodies. By default it renders
short evidence counts only. Add `debug_evidence=true` only for local debugging
when raw evidence refs are needed.

Export the processed document to the local Obsidian vault output:

```bash
uv run python scripts/export_obsidian_vault.py \
  --refresh-scores \
  --source-document-id SOURCE_DOCUMENT_ID
```

Obsidian is export-only. Do not manually edit generated vault files as source
data.

## Troubleshooting

- `401` with `API authentication failed`: API auth is enabled and the configured
  key is missing, the request header is missing, or the request key is wrong.
  Use `X-FounderOS-API-Key: YOUR_API_KEY` only with a key from your own local
  environment.
- `422` validation error: check that `title` and `text` are non-empty and that
  request fields match the schema above.
- Empty `extracted_items_preview`: the submitted text may not contain task, risk,
  or decision signals, or extracted entities without usable `evidence_refs` were
  skipped.
- Digest `400` with `start_at must be timezone-aware` or
  `end_at must be timezone-aware`: include an explicit timezone, such as
  `+00:00`, in the digest timestamp.
- Digest `400` with `end_at must be after start_at`: choose a digest window
  where `start_at` is earlier than `end_at`.
- Empty digest: no stored `SourceEvent` rows exist in the selected time window,
  or the selected window does not match the source activity timestamps.
- Empty rendered digest text: the selected source activity window is valid, but
  no stored `SourceEvent` rows exist for that window.
- Database connection errors: ensure `docker compose up -d postgres redis` is
  running and migrations have been applied.

## Safety Notes

- Do not paste real secrets, tokens, private keys, or credentials into sample
  text.
- Do not manually edit `.env`, `raw_storage`, or `obsidian_vault` as part of this
  flow.
- Extracted tasks, risks, and decisions must remain evidence-backed with
  `evidence_refs`.
- If evidence is missing, the system should return empty results, `null`, or
  insufficient evidence rather than inventing facts.
- LLM outputs used in pipelines must be strict JSON and validated before
  persistence, and LLMs must not directly mutate production data.
