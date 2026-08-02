# Secrets And Environment

FounderOS has one local runtime file at the repository root:
`.env.local`. It is ignored by git and is created or refreshed by the normal
local bootstrap. `.env.example` is the tracked, placeholder-only reference.
The application no longer loads a second `.env` file.

## The Boundary

There are two different classes of configuration:

| Class | Where it belongs | Why |
|---|---|---|
| OpenAI API key, model, reasoning level, output budget and policy acknowledgement | `Settings → AI` | Workspace-owned product configuration; the key is encrypted in PostgreSQL |
| GitHub App, GitHub fallback token, Jira API token, Gmail access token and Google Drive access token | `Settings → Integrations` | Workspace-owned connector configuration; secrets are encrypted in PostgreSQL |
| Database and Redis locations, raw-storage path, public URLs and CORS | `.env.local` locally or deployment configuration when hosted | FounderOS needs these before the database and UI can start |
| Repository Intelligence runtime path and checkout resource limits | `.env.local` locally or deployment configuration when hosted | The data path must resolve outside the FounderOS tree; these are execution-safety controls, not provider credentials |
| `FOUNDEROS_SECRET_ENCRYPTION_KEY` | `.env.local` locally or an infrastructure secret manager when hosted | This root key is required to decrypt workspace credentials; storing it inside the encrypted database would be circular |
| Recovery key file and off-device backup target | Founder-controlled infrastructure outside the repository | FounderOS must be recoverable even when the application machine or database is lost |
| Emergency kill switches, worker concurrency and timeouts | Runtime environment | These are deployment controls, not workspace credentials |

The interface intentionally never accepts the database URL, master encryption
key, recovery key, cookie/bootstrap authentication material or deployment
topology. A browser cannot safely repair the prerequisites needed to start that
browser and database.

## Product Credential Lifecycle

1. An owner or administrator enters a provider credential once in Settings.
2. FounderOS validates the bounded input and encrypts it before persistence.
3. Applying a setting does not silently call the provider.
4. The separate **Check connection** action performs the documented bounded
   read and stores only a safe receipt.
5. API responses return status booleans and safe labels, never plaintext or
   encrypted credential values.
6. Replacing a credential invalidates the previous check. Removing it clears
   the encrypted value and check state while preserving already imported
   canonical history.

GitHub App setup is fully product-managed. Its private key and OAuth secret are
created through the in-product manifest flow and encrypted in PostgreSQL. The
old environment-based GitHub App path and the manual installation-record
endpoint are removed.

AI runtime is also workspace-only. `ENABLE_LLM` remains an emergency server
kill switch, but it cannot provide a key or override the model, policy or
budget. If the workspace has no saved, enabled and successfully checked AI
configuration, FounderOS uses the deterministic local answer.

## Local Operation

- Run `make local` for the supported local bootstrap and start flow.
- Do not create or maintain a second `.env` file.
- Do not add provider keys to `.env.local`; the runtime ignores the former
  OpenAI and GitHub App environment names.
- Do not hand-edit generated bootstrap values during normal operation.
- Never commit `.env.local`, copy it into documentation or paste its values
  into diagnostics.

If the master encryption key is lost, existing provider credentials cannot be
recovered. Restore the separately protected recovery material or remove and
re-enter provider credentials through Settings. FounderOS must never guess,
log or export the lost plaintext.

## Current Product Gaps

- Jira uses an API token rather than OAuth.
- Gmail and Google Drive accept access tokens but do not yet implement the
  OAuth authorization-code flow, refresh-token rotation or automatic renewal.
- Hosted deployments still need an infrastructure secret manager/KMS boundary
  for the master encryption and recovery keys.
- Provider-side deletion remains separate from removing a FounderOS
  credential or canonical record.

These gaps are shown as product limitations; they are not worked around with
hidden environment credentials.
