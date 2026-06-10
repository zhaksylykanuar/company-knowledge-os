# Operator Runtime Setup

FounderOS uses the project root `.env` file as the primary local operator
configuration file. It is ignored by git and should contain only local secrets,
local credential locations, and local runtime switches needed for guarded local
work.

Do not commit `.env`. Do not paste its values into issues, chats, logs, docs,
or test output. Shell environment variables override values loaded from `.env`.

## Create The Local File

Start from the tracked placeholder template:

```bash
cp .env.example .env
```

Then edit `.env` locally. Keep the file shell-compatible:

```bash
KEY=
QUOTED_KEY=
```

Avoid shell commands, command substitutions, and unquoted values containing
spaces. Blank values in `.env` are treated as missing.

## Fill It Safely

Use placeholders only in `.env.example`; put real local values only in `.env`.
Do not put `<set locally>` or other placeholder text into `.env`, because
connector and operator checks treat blank and placeholder-like values as
missing. Generate any local random API auth value on your machine and paste it
into `.env` only.

Minimum FOS-036 Gmail validation keys:

```text
API_BASE_URL
API_AUTH_ENABLED
API_AUTH_KEY
API_AUTH_HEADER_NAME
GOOGLE_GMAIL_BACKFILL_ENABLED
GOOGLE_GMAIL_BACKFILL_QUERY
```

For persisted count validation, also configure the local database and raw
storage keys. For practical Gmail/Drive ingestion, configure Google client
secrets, token files, the Gmail bounded query, Drive folder boundary, and the
Google enable flags. For digest generation, configure the database/raw storage
runtime and enable LLM settings only when needed. For Telegram delivery,
configure the Telegram bot and chat keys.

Optional email thread-state key:

```text
EMAIL_ME_ADDRESSES
```

Use this only to help deterministic Gmail thread state classify whether the
last message was from the operator or from an external participant. It is
optional and must not block Google health checks; when it is missing, thread
state still builds but direction may remain `unknown` and status may be
`informational`.

Optional email digest triage keys:

```text
EMAIL_DIGEST_SHOW_LOW_PRIORITY
EMAIL_DIGEST_SHOW_MARKETING
EMAIL_DIGEST_SHOW_AUTOMATED
EMAIL_DIGEST_DEBUG_TRIAGE
EMAIL_DIGEST_DEBUG_EVIDENCE
EMAIL_IMPORTANT_SENDERS
EMAIL_IMPORTANT_DOMAINS
EMAIL_MARKETING_SENDER_BLOCKLIST
EMAIL_IMPORTANT_PROJECT_KEYWORDS
```

These keys are optional and default to safe, quiet digest behavior. Marketing,
newsletter, social, calendar, automated, and no-action security emails are
hidden from the main digest by default and summarized by count. Debug evidence
and debug triage are off by default because they can expose raw refs or rule
details intended only for explicit operator troubleshooting.

## Connector Configuration

GitHub and Jira connector config also use `.env` as the primary local file.
The legacy user config file under the operator's home directory remains a
fallback only. Connector scripts load allowlisted variables from `.env`, keep
configured shell environment values first, treat blank and placeholder-like
values as missing, and report configured/not_configured metadata without
printing values.

`FOS_GITHUB_TARGET_ORG` is an optional future organization-planning key. The
code also carries `qtwin-io` as safe target metadata, so current read-only
GitHub/Jira checks do not require this variable. The legacy repository overview
remains seed metadata only. The GitHub organization inventory CLI supports
default no-live, synthetic, and later manually acknowledged live-read-only
checks for counts/classes only; repository transfers or edits are not performed
by these scripts. Live organization inventory failures are reported as safe
operator classes such as authentication, permission, not-found/no-access,
rate-limit, server, transport, timeout, malformed-response, contract-mismatch,
or empty-inventory classes.

Atlassian/Jira credentials are separated by profile. The Jira read-only data
API profile uses the site REST API with a basic email/API-token auth class for
smoke, inventory, and read-only diagnostics. The future Jira write profile uses
the same site REST API auth class, but remains dry-run only. Atlassian Admin
profiles use a bearer admin API-key auth class plus Org ID presence metadata
for future admin diagnostics only; admin live calls and writes are disabled in
the current workflow. Keep all values in `.env` only.

Run the connector config doctor after local edits:

```bash
uv run python scripts/doctor_external_connector_config.py --json
```

Live read-only connector smoke checks remain a separate manual step and require
explicit acknowledgement. Default smoke mode is no-live, no-send, and no source
of truth mutation.

## Health Check

Run the safe local FOS-036 check without launching Codex:

```bash
./scripts/launch_codex_operator.sh --check-only
```

The check prints JSON metadata only: key presence, boolean parse status, path
existence booleans by key name, missing required keys, and final status. It does
not call Gmail, Drive, OpenAI, Telegram, OAuth, or smoke tests.

You can also run broader local checks directly:

```bash
python3 scripts/operator_env_health.py --mode google
python3 scripts/operator_env_health.py --mode full
```

## Launch Codex

After the FOS-036 health status is `ready`, launch Codex through the wrapper:

```bash
./scripts/launch_codex_operator.sh
```

The launcher starts at the repo root, loads `.env` into the environment, runs
the FOS-036 health check, and then executes Codex.

## Cleanup Planning

The ignored-file cleanup planner reports ignored and local files by safe
classes/counts only. It does not read ignored file contents and does not delete
anything by default.

```bash
uv run python scripts/report_ignored_file_cleanup_plan.py --json
```

Secret-like and env-like paths are suppressed in default output. Ambiguous
cleanup remains manual and review-gated.

## If Health Says Blocked

Open `.env` locally and fill the missing key names reported in
`missing_required_keys`. If a boolean key is invalid, use `true` or `false`.
If a required file path reports `exists: false`, create or point to the local
file before doing Google work. If a placeholder key is reported, replace the
placeholder with a real local value.

Run `./scripts/launch_codex_operator.sh --check-only` again. Keep iterating
until status is `ready`.
