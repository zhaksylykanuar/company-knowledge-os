# Feature: Gmail

## Status

- Current default: request-only/local/noop. The default Source Control registry
  does not wire a real Gmail client.
- Gmail read-only API wrapper library: implemented
- Gmail raw backfill request wrapper: implemented through Source Control
- Gmail backfill activation/query guardrail: implemented
- Gmail manual backfill limit guardrail: implemented
- Gmail manual backfill response redaction: implemented
- Google manual backfill preflight: implemented for safe guardrail inspection
- Gmail message to SourceDocument/chunks: implemented for readable message bodies
- Gmail write actions: planned and approval-gated

## Current Behavior

- Low-level Gmail read-only wrapper code exists, but the current default Source
  Control registry does not wire a real Gmail client. Operator-facing Source
  Control runs use local already-ingested records/noop behavior until a
  first-class real Google client is implemented and explicitly enabled.
- Preferred operator path is Source Control:
  `POST /v1/founder/sources/gmail/{preview_sync|backfill}` records a request,
  and `scripts/run_source_requests.py` advances that queued request through the
  orchestrator.
- The compatibility `POST /v1/gmail/backfill` route is request-only. It does
  not call Gmail connector code, write raw storage, or persist provider data.
  It records a redacted Source Control request instead.
- On the compatibility route, `persist=false` maps to a `preview_sync` request
  and `persist=true` maps to a `backfill` request for the orchestrator; the
  wrapper itself never performs the live Gmail read.
- An explicit Gmail query on the compatibility route must be non-blank and
  narrower than the historical broad `in:inbox OR in:sent` query. The raw query
  is not stored or returned. If omitted, the route records only that the
  configured query path was selected.
- Gmail request wrappers use a safe default of 10 messages per request and a
  hard API maximum of 50 messages per request.
- Gmail request wrapper responses are redacted by default and return request
  IDs, status, action type, source type, safe limits, and sanitized input flags
  instead of snippets, subjects, email addresses, attachment names, provider
  message IDs, thread IDs, or raw event payloads.
- The protected Google preflight endpoint can validate Gmail backfill readiness
  and safe local Google credential file presence without calling Gmail APIs,
  reading credential contents, or returning the query value, credential paths,
  token paths, or credential values.
- Local manual Gmail backfill testing should follow
  `../runbooks/google-local-backfill.md`.
- Raw Gmail messages, threads, messages, and attachment metadata are persisted
  only by approved connector/orchestrator execution paths, not by the
  compatibility HTTP wrapper itself.
- Deterministic email thread state can be rebuilt from stored Gmail rows with
  no live Gmail or LLM calls. The MVP stores one state row per detected
  conversation using Gmail thread IDs first, then message-header relationships,
  then normalized subject plus overlapping participants.
- The source activity digest uses `EmailThreadState` rows as the primary Gmail
  source data when thread states exist for the digest window. Each row includes
  deterministic triage fields: `triage_category`, `triage_action_type`,
  `triage_priority`, `show_in_digest`, `triage_reason`, and
  `triage_confidence`. Thread `status` is derived from triage action type
  rather than only the last sender. Digest sectioning projects those
  deterministic fields into an in-memory `AttentionTriageResult` and applies
  the shared confidence policy before mapping to sections.
- Email triage separates technical reply state from business/action relevance.
  Work questions become reply-required work actions, outbound work threads
  become waiting-for-external-reply items, badge/ticket/access/registration
  readiness becomes manual action, suspicious security alerts become high
  priority manual action, and uncertain work-like messages remain visible for
  optional review. Marketing, newsletters, social notifications, calendar
  auto-updates, automated notifications, and no-action security alerts are
  hidden from main digest sections by default and summarized by count.
- The source activity digest email sections are ordered as: work actions
  requiring attention, manual actions, waiting for external reply, important
  project updates, review optional, and hidden low-priority email summary.
  Normal digest text shows short evidence counts; raw evidence refs and triage
  details are debug-only.
- Gmail emits registry-compatible `gmail.message.ingested` events with `source_object_type` and `subject` when a Subject header is present.
- Gmail messages with readable `text/plain` body content, or `text/html` body content when no plain text exists, are converted into `source_documents` and `document_chunks`.
- Gmail messages without readable body text are skipped for document/chunk creation.
- Gmail connector/orchestrator backfill can create SourceEvent rows for new
  ingested message events when registry-required fields are present.
- Persisted Gmail message SourceEvent rows can be projected into
  `NormalizedActivityItem` rows with `activity_type="email.received"` for
  explicit local attention triage windows.
- Gmail messages without a real Subject header do not get SourceEvent rows in this ticket; no subject is invented.

## Invariants

- Gmail access is read-only first.
- Tokens must stay backend-only.
- Raw messages must be stored before downstream processing.
- Write actions require future explicit approval flow.
- Email triage is deterministic by default and does not call Gmail, OpenAI, or
  any other external API.

## Operator Configuration

Optional email digest keys:

- `EMAIL_DIGEST_SHOW_LOW_PRIORITY=false`
- `EMAIL_DIGEST_SHOW_MARKETING=false`
- `EMAIL_DIGEST_SHOW_AUTOMATED=false`
- `EMAIL_DIGEST_DEBUG_TRIAGE=false`
- `EMAIL_DIGEST_DEBUG_EVIDENCE=false`
- `EMAIL_IMPORTANT_SENDERS=`
- `EMAIL_IMPORTANT_DOMAINS=`
- `EMAIL_MARKETING_SENDER_BLOCKLIST=`
- `EMAIL_IMPORTANT_PROJECT_KEYWORDS=`

These keys are optional and must not block operator health checks. Allowlists
and blocklists are comma-separated. Debug evidence can include raw refs, and
debug triage can show rule names/confidence, so both remain off by default.

## Known Gaps

- Gmail attachment content ingestion is not implemented; attachments remain metadata-only.
- Webhook/PubSub handling is not visible as implemented.
- Production Gmail sync, pagination, incremental history sync, token refresh,
  production token storage, and OAuth hardening are not implemented.
