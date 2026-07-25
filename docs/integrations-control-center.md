# Integrations Control Center

`/settings/integrations` is the workspace-scoped control surface for GitHub,
Jira Cloud, Gmail, and Google Drive credentials. It is a configuration and
verification layer over the existing `IntegrationConnection` model, not a
second connector engine or a provider-specific product area.

## Product Flow

The default UI exposes only two steps:

1. save or replace the supported connection;
2. run the explicit read check.

The read check stays disabled until a connection exists. Empty receipts are not
rendered. Write-readiness, credential removal, and the GitHub personal-token
fallback remain available under progressive disclosure instead of competing
with first-time setup. Every provider is selected directly inside
`/settings/integrations?provider=<provider>`. Jira, Gmail, and Drive keep manual
JSON import only as a collapsed developer fallback.

## Security Boundary

- Only a workspace owner or administrator may save credentials or run checks.
  Members and viewers may see safe status only.
- The browser sends a secret once over the same-origin authenticated request.
  The backend encrypts it before persistence in
  `integration_connections.encrypted_access_token`.
- API responses never return encrypted values, token hints, raw provider
  payloads, connection UUIDs, installation IDs, or refresh tokens.
- Every workspace connector response uses `Cache-Control: private, no-store`
  at the ASGI boundary, including authentication, authorization, validation
  and application errors created before endpoint execution.
- Applying a configuration makes no provider request and leaves it
  `saved_unverified`.
- A read check is an explicit bounded GET request to a fixed provider endpoint.
  It stores only a safe receipt and promotes a successful connection to
  `read_verified`.
- A write check is always a local dry-run. It does not decrypt a credential,
  call a provider, or perform an external write.
- A credential saved through this control center can be explicitly removed
  after an additional UI confirmation. The encrypted value, account label,
  scopes and check receipts are cleared; the durable connection row, imported
  canonical data and sync history remain. Managed GitHub App credentials stay
  owned by the GitHub setup flow.
- Real GitHub writes remain exclusively behind the existing approved
  `ActionProposal` execution contract, write feature flag, repository allowlist,
  evidence, idempotency, and read-back reconciliation.
- A workspace-scoped product read may use only canonical `Repository` rows for
  that exact workspace. If none exist, the inventory is empty. Global
  `SourceEvent`, discovery-snapshot, and legacy-file fallbacks are restricted to
  explicit unscoped operator/script reads and can never populate another
  workspace's GitHub integration surface.

Jira accepts only an HTTPS `*.atlassian.net` site without credentials, custom
port, path, query, or fragment. GitHub, Gmail, and Drive use fixed official API
hosts. The control center does not accept arbitrary API base URLs.

## Provider Matrix

| Provider | Configuration method | Read check | Write check | Current gap |
|---|---|---|---|---|
| GitHub | Managed workspace GitHub App (recommended) or personal access token fallback | JIT installation token + repository list, or `GET /user` | Dry-run of credential/read/write/approval/allowlist gates | A real write still requires an exact approved ActionProposal and repository target |
| Jira Cloud | Site URL + account email + Atlassian API token | `GET /rest/api/3/myself` | Guarded dry-run; provider write not implemented | OAuth and any Jira external-write executor are absent |
| Gmail | Manual OAuth access token | `GET /gmail/v1/users/me/profile` | Guarded dry-run; provider write not implemented | OAuth authorization-code flow, refresh-token storage/rotation, and automatic renewal are absent |
| Google Drive | Manual OAuth access token | `GET /drive/v3/about?fields=user(...)` | Guarded dry-run; provider write not implemented | OAuth authorization-code flow, refresh-token storage/rotation, and automatic renewal are absent |

Manual Google access tokens can expire. The UI states this explicitly and does
not claim automatic refresh.

## API Contract

All routes are under
`/api/v1/workspaces/{workspace_id}/connectors`:

- `GET /control-center` — safe status projection; no secret read or provider
  call.
- `POST /{provider}/configuration` — validate, encrypt, and save one supported
  configuration; owner/admin only.
- `DELETE /{provider}/configuration` — remove only the credential saved through
  this control center while preserving the durable row and imported history;
  owner/admin only.
- `POST /{provider}/checks/read` — explicit bounded provider read; owner/admin
  only.
- `POST /{provider}/checks/write` — local readiness receipt; owner/admin only,
  no provider call.

Safe receipts live in `IntegrationConnection.provider_metadata.control_center`
with contract version `connector-control.v1`. No migration is required. Raw
storage and PostgreSQL remain the sources of truth; Obsidian remains
export-only.

## Runtime Configuration

The UI never reads `.env` and never writes environment variables. Runtime gates
remain process configuration:

| Variable | Purpose |
|---|---|
| `FOUNDEROS_SECRET_ENCRYPTION_KEY` | Dedicated credential-encryption material; required outside local/dev |
| `FOUNDEROS_CONNECTOR_NETWORK_TIMEOUT_SECONDS` | Bounded read-check timeout |
| `FOUNDEROS_ENABLE_REAL_CONNECTORS` | Required for operator/API-key initiated provider checks; explicit authenticated product actions use the existing user-confirmed provider boundary |
| `ENABLE_WRITE_ACTIONS` | Enables the existing external ActionProposal executor; does not make the dry-run write check perform a write |
| `REQUIRE_APPROVAL_FOR_WRITES` | Keeps external execution behind human approval |
| `FOS_GITHUB_WRITE_ALLOWED_REPOS` | Exact repository allowlist used by GitHub write readiness and execution |

Changing these variables requires a runtime restart. Never place real values in
documentation, tracked `.env` files, screenshots, test fixtures, or issue
comments.

## State Model

1. `not_configured` — no supported stored credential.
2. `saved_unverified` — encrypted configuration exists, but a read has not
   succeeded.
3. `read_verified` — the latest bounded read check passed.
4. `error` — the latest read check failed or the stored connection is in an
   error state.

The status projection can be read without decrypting credentials. Replacing a
secret resets read and write receipts so a previous verification cannot be
mistaken for proof of the new credential.

Removing a credential returns the provider to `not_configured`. A failed check
that stops before any network request records
`provider_call_performed=false`; a receipt may claim a provider call only after
the network boundary was actually attempted.
