# Runbook: Manual MVP Pilot

This runbook is for a developer-operated 5-day manual pilot. It keeps the pilot
read-only and draft-only unless a later, explicit approval/action layer exists.

## First Check: Synthetic Dry Run

Run the synthetic readiness check from a clean local checkout:

```bash
.venv/bin/python scripts/pilot_dry_run.py --format json
.venv/bin/python scripts/pilot_dry_run.py --format text
```

The dry run uses synthetic sample data only. It does not read local private
data, open DB sessions, call providers, call source APIs, run ingestion, run
migrations, write files, create Jira issues, send Telegram/Slack messages, or
write KB/Obsidian output.

Review the output sections:

- `attention_policy_sample`
- `digest_sections_sample`
- `source_normalization_sample`
- `meeting_draft_sample`
- `feedback_context_shape_sample`
- `deferred_boundaries`
- `safety`

Stop before the pilot if the safety section does not report provider-free,
no external API calls, no DB writes, no ingestion, no migrations, no Jira
writes, no KB/Obsidian writes, and synthetic data only.

## Day 0 Setup

- Confirm the git tree is clean.
- Confirm local services and migrations are prepared only for the manual flows
  that intentionally need local DB-backed endpoints.
- Confirm no real source backfill, webhook, scheduled digest, Jira creation, or
  KB write will run as part of this pilot.
- Pick safe pilot inputs that can be reviewed manually.
- Do not paste secrets, credentials, private provider payloads, or broad raw
  source content into notes, tickets, docs, or chat.

## Days 1-5 Manual Loop

1. Start with the dry-run command and confirm the safety section.
2. Use the manual knowledge quickstart for explicitly provided safe notes.
3. Review attention and digest previews manually.
4. Use meeting transcript draft outputs only as proposed artifacts.
5. Record user feedback in a controlled follow-up path; feedback-aware live
   triage wiring is still deferred.
6. Treat Jira draft tickets and KB update drafts as inert drafts until a human
   approval/action layer exists.
7. End each day by checking the git tree is clean and no generated KB/Obsidian
   files were manually edited as source data.

## Daily Founder Digest v2 Loop (current pilot shape)

Run by a human, in order, with a fresh window each day. Guard phrases are typed
by the human on purpose; agents must not supply them.

1. Backfill the fresh Gmail/Drive window (see
   `google-local-backfill.md`).
2. Normalize stored source events
   (`scripts/normalize_stored_source_events.py`, preview first).
3. Triage with the LLM provider (this is the step that makes the digest
   meaningful; the fallback provider puts everything in review_optional):
   `ENABLE_LLM=true uv run python scripts/triage_normalized_activity_items.py
   --provider openai --acknowledge-live-provider-risk
   "ALLOW LIVE PROVIDER EXECUTION" ...window args...`
4. Preview the founder digest before drafting:
   `uv run python scripts/preview_founder_digest.py --start-at ... --end-at ...`
5. Prepare the delivery draft in the founder v2 style:
   `uv run python scripts/prepare_no_marker_persisted_attention_delivery_draft.py
   --digest-style founder_v2 --confirm-prepare "PREPARE NO-MARKER DIGEST DRAFT"
   ...window args...`
6. Approve, create the intention, and send through the existing gated chain.
7. Read the digest in Telegram, mark noise/important items, and convert every
   miss into an eval case in `tests/evals/`.

Pick the digest style per window before the first send of that window: the
style changes `text_sha256`, and the duplicate-success guard is hash-based, so
re-sending the same window in a different style would not be auto-blocked
(see the presentation-variant analysis in `docs/features/attention.md`).

## Founder Bot (pull Q&A, vision Phase A1)

Operator-launched long-polling bot. Read-only: answers only the allowlisted
founder chat with the founder digest v2 over a trailing window. The human
types the guard phrase on purpose:

```bash
uv run python scripts/run_telegram_founder_bot.py \
  --acknowledge-live-provider-risk "ALLOW LIVE PROVIDER EXECUTION" \
  --window-hours 24
```

Commands: `/status` (also plain text mentioning "статус"/"что у нас"),
`/help`. Messages from any other chat are ignored. Stop with Ctrl+C. The bot
performs no DB writes and creates no drafts/intentions/results.

## Human Approval Boundary

AI-generated or deterministic draft artifacts are not actions. A human must
approve before any future workflow creates Jira issues, writes KB/Obsidian
files, sends delivery messages, or mutates production data.

## Deferred During This Pilot

- Live source API connectors and webhooks.
- Scheduled digest.
- Telegram/Slack delivery.
- Feedback buttons/actions.
- Feedback-aware live triage wiring.
- `AttentionTriageResult` persistence.
- `normalized_activity_items` persistence.
- Human approval/action execution.
- Jira creation after approval.
- KB/Obsidian writes after approval.
- PR review agent.

## Stop Conditions

Stop and investigate if any of these happen:

- The dry-run safety section reports a write, API call, ingestion, migration, or
  non-synthetic input.
- A command unexpectedly reads credentials, private data, raw storage, or the
  generated Obsidian vault.
- A live source API, provider, Jira, Telegram, Slack, or Google call happens.
- A DB write happens outside an explicitly approved local manual endpoint.
- A Jira issue, KB file, or Obsidian file is created by the pilot workflow.
- The git tree becomes dirty unexpectedly.
