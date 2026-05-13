# Feature: Gmail

## Status

- Gmail read-only API wrapper: implemented
- Gmail raw backfill: partial
- Gmail backfill activation/query guardrail: implemented
- Gmail manual backfill limit guardrail: implemented
- Gmail manual backfill response redaction: implemented
- Google manual backfill preflight: implemented for safe guardrail inspection
- Gmail message to SourceDocument/chunks: implemented for readable message bodies
- Gmail write actions: planned and approval-gated

## Current Behavior

- Gmail messages can be listed and fetched with read-only scope.
- Gmail backfill is disabled by default and must be explicitly enabled before
  the route calls connector code.
- Enabled Gmail backfill requires a narrower explicit query or configured safe
  query. The historical broad `in:inbox OR in:sent` query is rejected.
- Manual Gmail backfill uses a safe default of 10 messages per request and a
  hard API maximum of 50 messages per request.
- Manual Gmail backfill responses are redacted by default and return safe
  counts/status fields instead of snippets, subjects, email addresses,
  attachment names, provider message IDs, thread IDs, or raw event payloads.
- The protected Google preflight endpoint can validate Gmail backfill readiness
  and safe local Google credential file presence without calling Gmail APIs,
  reading credential contents, or returning the query value, credential paths,
  token paths, or credential values.
- Local manual Gmail backfill testing should follow
  `../runbooks/google-local-backfill.md`.
- Raw Gmail messages are stored under raw storage.
- Threads, messages, and attachment metadata are persisted.
- Deterministic email thread state can be rebuilt from stored Gmail rows with
  no live Gmail or LLM calls. The MVP stores one state row per detected
  conversation using Gmail thread IDs first, then message-header relationships,
  then normalized subject plus overlapping participants.
- The source activity digest uses `EmailThreadState` rows as the primary Gmail
  output when thread states exist for the digest window. Each row includes
  deterministic triage fields: `triage_category`, `triage_action_type`,
  `triage_priority`, `show_in_digest`, `triage_reason`, and
  `triage_confidence`. Thread `status` is derived from triage action type
  rather than only the last sender.
- Email triage separates technical reply state from business/action relevance.
  Work questions become reply-required work actions, outbound work threads
  become waiting-for-external-reply items, badge/ticket/access/registration
  readiness becomes manual action, suspicious security alerts become high
  priority manual action, and uncertain work-like messages remain visible for
  optional review. Marketing, newsletters, social notifications, calendar
  auto-updates, automated notifications, and no-action security alerts are
  hidden from main digest sections by default and summarized by count.
- The source activity digest email sections are ordered as: work actions
  requiring attention, manual actions, waiting for external reply, work info /
  recently relevant, review optional, and hidden low-priority email summary.
  Normal digest text shows short evidence counts; raw evidence refs and triage
  details are debug-only.
- Gmail emits registry-compatible `gmail.message.ingested` events with `source_object_type` and `subject` when a Subject header is present.
- Gmail messages with readable `text/plain` body content, or `text/html` body content when no plain text exists, are converted into `source_documents` and `document_chunks`.
- Gmail messages without readable body text are skipped for document/chunk creation.
- Gmail `persist=true` backfill creates SourceEvent rows for new ingested message events when registry-required fields are present.
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
