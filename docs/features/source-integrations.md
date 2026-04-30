# Feature Contract: Source Integrations And Credentials

FOS-019 defines the setup contract for future real external source
connectivity. It is documentation only. It does not implement connectors,
OAuth, webhooks, schedulers, Telegram inbound flows, or production sync.

## Current Status

- Manual ingest/process MVP: implemented through
  `POST /v1/knowledge/ingest-text-process`.
- Gmail: partial read-only foundation. The repo can list/fetch messages with
  read-only OAuth, store raw messages, persist Gmail read models, create source
  documents and chunks for readable message bodies, and normalize valid new
  message events into `SourceEvent` rows.
- Google Drive: partial read-only foundation. The repo can list a configured
  Drive AI inbox folder, download/export text content when supported, store raw
  snapshots, create source documents and chunks, and normalize valid new file
  events into `SourceEvent` rows.
- GitHub repositories, including `qaztwin`: registry contracts, fixtures, and
  connector payload mapping exist, but there is no real production GitHub
  connector or webhook endpoint yet.
- Jira: registry contracts, fixtures, and connector payload mapping exist, but
  there is no real production Jira connector yet.
- Calendar: planned for later.
- Meeting transcripts: planned for later.
- Telegram outbound delivery: implemented as a service adapter for
  already-rendered plain text.
- Telegram inbound notes, Telegram Q&A, and daily scheduler: not implemented.

## Source Of Truth Rules

- Raw storage and Postgres are authoritative.
- Obsidian is export-only.
- Telegram is an interface and delivery channel, not the source of truth.
- ChatGPT and the OpenAI API are not the database or source of truth.
- External APIs provide raw events and raw/source documents. They are not
  trusted interpreted company knowledge by themselves.
- Extraction, retrieval, Q&A, and digest generation must run from stored data,
  not directly from live provider responses.

## Source Identity Contract

Each source event or source document should be traceable to a stable source
identity before it is used downstream.

Recommended identity fields:

- `provider`: external source family, such as `gmail`, `google_drive`,
  `github`, `jira`, `calendar`, `meeting_transcript`, or `telegram`.
- `source_system`: persisted system value where applicable. Existing
  implemented values include `gmail`, `drive`, `github`, `jira`, `telegram`,
  and `internal`; `google_drive` maps to the existing `drive` value unless a
  future migration explicitly changes that.
- `account_id` or `workspace_id`: the user, tenant, organization, workspace, or
  site boundary that granted access.
- `external_object_id`: provider object ID, such as Gmail message ID, Drive file
  ID, GitHub pull request URL/number, Jira issue key, Calendar event ID, or
  transcript file ID.
- `source_object_type`: object class, such as `message`, `file`,
  `pull_request`, `issue`, `sprint`, `calendar_event`, `transcript`, or
  `telegram_message`.
- `event_type`: provider event type, such as `gmail.message.ingested`,
  `drive.file.ingested`, `github.pull_request.opened`,
  `jira.issue.status_changed`, or a future Calendar/transcript event.
- `source_document_id`: stable document ID when the source has document-like
  content that becomes `SourceDocument` and `DocumentChunk` rows.
- `repository_full_name`: for GitHub, use `owner/repo`; `qaztwin` is the
  project-specific example repository/source and must still be placed behind an
  explicit repository allowlist.
- `jira_site`, `jira_project_key`, and `jira_issue_key`: for Jira source
  identity and allowlist checks.
- `provider_event_ts`: the provider timestamp for the source event.
- `ingested_at`: the backend ingestion timestamp.
- `raw_object_ref`: pointer to the raw stored snapshot.
- `evidence_refs`: downstream pointers back to source events, source
  documents, chunks, raw refs, or source URLs.

## Credentials And Secret Handling

- Do not commit real secrets, tokens, API keys, OAuth refresh tokens, private
  keys, private emails, customer data, repository secrets, Telegram chat IDs, or
  Telegram bot tokens.
- Do not edit `.env` in tickets. `.env` is local only and must stay ignored.
- Production must use a secret manager or deployment secret store, not committed
  config files.
- Tokens and secrets must not appear in logs, error messages, docs examples,
  test snapshots, digest text, Telegram messages, or returned API payloads.
- Use least-privilege scopes for every provider.
- Rotate credentials immediately if they are leaked or suspected leaked.
- Separate personal user Google access from team/workspace access where
  applicable.
- Team GitHub and Jira credentials must be approved by the team or workspace
  owner before use.

Use placeholders only in docs and tests, for example:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY`
- `JIRA_BASE_URL`
- `JIRA_API_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Per-Source Credential Expectations

### Gmail And Google Drive

- Use OAuth client credentials and explicit user consent.
- Prefer read-only scopes first.
- Store OAuth tokens only in local ignored files or a production secret store.
- Keep user personal Google access separate from team/workspace access where
  applicable.
- Do not broaden scopes without a ticket that explains the user-facing need and
  approval boundary.

### GitHub Team Repositories

- Prefer a GitHub App or fine-grained token with read-only repository activity
  permissions for the initial connector.
- Require a repository allowlist. Include `qaztwin` as a project-specific
  example source only when the owning team approves it.
- Store private keys, app secrets, and tokens only in ignored local files or a
  production secret store.
- Webhook secrets must never be logged or returned to clients.

### Jira

- Require a Jira base URL/site boundary, project allowlist, and approved API
  token or OAuth policy.
- Start read-only.
- Keep issue keys, sprint IDs, and project keys as source identity fields.
- Do not perform write actions without a future explicit approval workflow.

### Calendar

- Planned later.
- Require explicit OAuth scopes and a calendar allowlist before ingestion.
- Persist raw event snapshots before extraction, digest, or Q&A use.

### Meeting Transcripts

- Planned later.
- Require a clear upload/source policy, source owner, and raw file handling
  rule before ingestion.
- Store raw transcript files before chunking or extraction.
- Avoid putting private transcript text in docs, tests, logs, or Telegram
  messages.

### Telegram

- Outbound delivery uses a bot token and chat ID for already-rendered plain
  text.
- Inbound bot messages, founder notes, approvals, and Q&A are planned later.
- Telegram messages can become source events only when intentionally ingested.
- Telegram is never the database or source of truth.

## Activation And Allowlist Rules

- Each integration must be explicitly enabled.
- Each provider must have a scope or allowlist boundary.
- There must be no "sync everything" default.
- Start read-only.
- Persist raw snapshots and source events first.
- Extraction, digest, and Q&A must use stored data, not live API responses.
- Failures must be visible through logs, audit records, or returned status; they
  must not be silently ignored.
- Connector behavior must be deterministic and idempotent where provider data
  permits it.

## Webhook And Sync Safety

- Provider webhook signature verification is required before accepting webhook
  events in production.
- Idempotency and deduplication are required for every external event.
- Replay handling is required for webhook or queued delivery.
- Provider timestamps and ingestion timestamps both matter.
- LLM outputs must not directly mutate production data.
- Scheduler and daily jobs are future work and must use explicit time windows.
- Raw snapshots must be stored before extraction, digest, or Q&A use.

## Evidence Requirements

- Source events, source documents, and document chunks must create evidence
  pointers.
- Extracted tasks, risks, and decisions must include `evidence_refs`.
- Digest output must distinguish source activity from interpreted decisions,
  tasks, and risks.
- Q&A must retrieve stored evidence first.
- If evidence is insufficient, Q&A must say so instead of guessing.
- Evidence-free extracted items must not be presented as trusted knowledge.

## Recommended Connection Order

1. Gmail production-readiness hardening.
2. Google Drive production-readiness hardening.
3. GitHub or `qaztwin` mapper/connector v0.
4. Jira mapper/connector v0.
5. Calendar.
6. Meeting transcripts.
7. Telegram inbound notes and Q&A.
8. Scheduler and daily digest delivery.

This order keeps the source-of-truth boundary ahead of user-facing automation:
raw storage and Postgres first, evidence-backed extraction second, Telegram
delivery and Q&A last.
