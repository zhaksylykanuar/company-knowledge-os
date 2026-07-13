# External Action Result Smoke Runbook

Status: manual, human-approved, write-capable smoke only. This runbook exists
for the final MVP flow step:

```text
Approve Action Proposal -> See External Action Result
```

It must **not** be run as part of normal read-only local smoke. It is only for a
short, explicitly approved window after the current local stack is verified,
the scoped provider read has passed, GitHub App/provider credentials are
configured server-side, and the human has selected exactly one safe target
repository. It must not be run as part of normal read-only local smoke.

## Safety boundary

This procedure is intentionally manual. It does not add automation, CI,
workflow dispatch, provider writes, deploy commands, secret reads, or LLM calls.
Do not paste real secrets, tokens, chat IDs, database URLs, raw provider
payloads, private issue URLs, local proposal IDs, local workspace IDs, or
production smoke response bodies into docs, chat, commits, or tickets.

Required boundaries:

- One explicitly approved external write only.
- One allowlisted repository only.
- One ActionProposal only.
- Evidence refs must be present before execution.
- Human approval must be recorded before execution.
- `REQUIRE_APPROVAL_FOR_WRITES` stays enabled.
- `ENABLE_WRITE_ACTIONS` may be enabled only for the approved smoke window.
- `FOS_GITHUB_WRITE_ALLOWED_REPOS` must include only the approved smoke target.
- No selected repository issue/PR sync, GitHub App real read, provider-token
  setup, local startup, migration, or LLM call is part of this runbook.
- After the smoke, disable write capability again unless the human explicitly
  approves keeping it on.

## Preconditions

Before starting, verify all of these are true:

1. The exact reviewed code is running through `make local` and
   `make local-doctor` reports no required blocker.
2. `make local-smoke` passed against that verified local stack.
3. The GitHub connection/write path is configured server-side only; no browser
   token or operator key is pasted into the UI.
4. The approved target repository is safe for a single smoke issue.
5. Runtime env is scoped for the smoke:
   - `ENABLE_WRITE_ACTIONS=true` only during the approved window.
   - `REQUIRE_APPROVAL_FOR_WRITES=true`.
   - `FOS_GITHUB_WRITE_ALLOWED_REPOS=<approved-owner/repo>`.
6. The ActionProposal has non-empty `evidence_refs`.
7. The human has approved the exact title/body/target repository before execute.

If any precondition is false, stop and return to read-only mode.

## Open the bounded write window

Canonical `make local` intentionally refuses live-provider or write gates. Stop
it first:

```bash
make local-stop
```

In a dedicated backend terminal, set only the approved window flags and start
the reviewed backend directly. Keep the allowlist to one repository:

```bash
export FOUNDEROS_ENABLE_REAL_CONNECTORS=true
export ENABLE_WRITE_ACTIONS=true
export REQUIRE_APPROVAL_FOR_WRITES=true
export FOS_GITHUB_WRITE_ALLOWED_REPOS=<approved-owner/repo>
export ENABLE_LLM=false
UV_NO_SYNC=1 uv run uvicorn app.main:app \
  --host 127.0.0.1 --port 8765 --no-access-log
```

In a second terminal, start the local web proxy:

```bash
cd web
FOUNDEROS_API_PROXY_TARGET=http://127.0.0.1:8765 \
  npm run dev -- --hostname 127.0.0.1 --port 3000
```

Do not proceed if the preview says live execution is disabled or `/health`
fails through `http://127.0.0.1:3000`.

## Preferred product UI path

Use the product UI when possible:

1. Sign in as the founder/admin.
2. Open `/actions`.
3. Create or select exactly one GitHub issue proposal for the approved smoke
   repository.
4. Open its evidence refs and verify the claim is supported.
5. Approve the proposal locally.
6. Open execution preview and verify:
   - provider is GitHub;
   - action is create issue;
   - repository matches the allowlist;
   - title/body are safe;
   - evidence refs are present;
   - backend capabilities say a live write is allowed.
7. Confirm external execution once.
8. Verify the UI shows a receipt/audit event for the external action result.
9. Do not repeat execute if a successful receipt already exists.

## API fallback path

Use this only if the UI cannot complete the smoke. Replace placeholders locally
and never commit or paste real values.

1. Fetch the execution preview:

   ```bash
   curl -fsS \
     -H '<api-key-header>: <api-key>' \
     '<api-base>/api/v1/workspaces/<workspace-id>/actions/proposals/<proposal-id>/execution-preview'
   ```

2. Execute exactly once after checking the preview:

   ```bash
   curl -fsS -X POST \
     -H '<api-key-header>: <api-key>' \
     -H 'Content-Type: application/json' \
     -d '{"connection_id":"<github-connection-id>","confirm_external_write":true,"idempotency_key":"<unique-smoke-key>"}' \
     '<api-base>/api/v1/workspaces/<workspace-id>/actions/proposals/<proposal-id>/execute'
   ```

3. Read back and normalize the execution result:

   ```bash
   curl -fsS -X POST \
     -H '<api-key-header>: <api-key>' \
     '<api-base>/api/v1/workspaces/<workspace-id>/actions/proposals/<proposal-id>/sync-execution-result'
   ```

4. Record only sanitized facts in the private operator log:
   - smoke executed: yes/no;
   - backend status code class;
   - receipt present: yes/no;
   - Company Brain sees the normalized result: yes/no;
   - any blocker category, without raw response bodies.

Do not paste raw provider responses, GitHub issue URLs, internal IDs, tokens, or
payload bodies into repository docs.

After the one approved result is verified, stop both temporary processes,
unset all four write-window variables, restore any private env entries to their
disabled values, run `make local-doctor`, and restart canonical `make local`.

## Verification checklist

The smoke is successful only when all checks pass:

- A single approved ActionProposal has exactly one successful `ActionExecution`.
- A durable audit timeline includes preview, confirmation, started, and succeeded
  events.
- Duplicate execute does not create a second provider issue; it returns/uses the
  existing receipt.
- `sync-execution-result` reads back the created provider issue and normalizes it
  into canonical `SourceRecord` + `Task` data.
- Dashboard, Company Brain, operational work, and deterministic briefing can see
  the normalized result through evidence-backed local state.
- ENABLE_WRITE_ACTIONS is disabled again after the smoke;
  `FOUNDEROS_ENABLE_REAL_CONNECTORS` is also disabled and the one-repository
  allowlist is cleared after the smoke window.

## Rollback / cleanup boundary

If the smoke creates an issue that should not remain open, close exactly that
smoke issue manually after separate human approval, then run the read-back sync
for the same proposal/result. Do not edit unrelated issues, labels, assignees,
repository settings, pull requests, releases, or files.

If any step fails:

1. Stop both temporary backend/frontend processes; do not execute another write.
2. Set `ENABLE_WRITE_ACTIONS=false` and
   `FOUNDEROS_ENABLE_REAL_CONNECTORS=false`; unset
   `FOS_GITHUB_WRITE_ALLOWED_REPOS` and `REQUIRE_APPROVAL_FOR_WRITES` in the
   temporary shell, and restore any private env entries to disabled values.
3. Preserve local audit rows and server logs for private diagnosis.
4. Report only sanitized status and blocker category.
5. Do not retry until the human approves a new idempotency key or confirms the
   previous receipt was not created.

## Relationship to other runbooks

Run order for full MVP proof:

1. `docs/operations/local-runtime.md` — start and verify the local stack.
2. `docs/deploy/github-app-first-real-read-run.md` — first scoped read-only
   GitHub App provider read.
3. This runbook — one explicitly approved external action result smoke.

This runbook is deliberately not referenced by CI, `make local-smoke`, or
automatic workflows.
