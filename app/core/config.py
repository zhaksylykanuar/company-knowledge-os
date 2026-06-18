from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_local_workspace_path() -> str:
    return str(Path(__file__).resolve().parents[2] / ".local")


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "company-knowledge-os"
    api_base_url: str = "http://localhost:8000"

    # --- Local dev bootstrap (safe to surface to the browser in local) ---
    # The base URL the browser should call, the dev API key handed to the
    # browser, and whether the browser dev-config endpoint is enabled. None
    # of these are external/third-party secrets.
    founderos_api_base_url: str = Field(
        default="http://127.0.0.1:8765",
        validation_alias=AliasChoices("FOUNDEROS_API_BASE_URL"),
    )
    dev_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_DEV_API_KEY"),
    )
    enable_browser_dev_config: bool = Field(
        default=False,
        validation_alias=AliasChoices("FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG"),
    )
    # Comma-separated list of API keys the backend accepts (in addition to
    # api_auth_key). Lets a local dev key authenticate the local backend.
    api_keys: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_API_KEYS"),
    )
    founderos_local_workspace_path: str = Field(
        default_factory=_default_local_workspace_path,
        validation_alias=AliasChoices("FOUNDEROS_LOCAL_WORKSPACE_PATH"),
    )

    database_url: str = "postgresql+asyncpg://ckdos:ckdos_dev_password@localhost:5432/ckdos"
    redis_url: str = "redis://localhost:6379/0"

    raw_storage_dir: str = "./raw_storage"

    enable_llm: bool = False
    enable_write_actions: bool = False
    enable_obsidian_export: bool = True
    require_approval_for_writes: bool = True
    enable_obsidian_bridge: bool = Field(
        default=False,
        validation_alias=AliasChoices("FOUNDEROS_ENABLE_OBSIDIAN_BRIDGE"),
    )
    obsidian_bridge_vault_name: str = Field(
        default="FounderOS Knowledge Vault",
        validation_alias=AliasChoices("FOUNDEROS_OBSIDIAN_VAULT_NAME"),
    )
    obsidian_bridge_vault_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_OBSIDIAN_VAULT_PATH"),
    )
    obsidian_bridge_sync_mode: str = Field(
        default="manual",
        validation_alias=AliasChoices("FOUNDEROS_OBSIDIAN_SYNC_MODE"),
    )

    # --- Real read-only connector execution (opt-in; default OFF) ---
    # When false, real Jira/GitHub clients never make a network call; only
    # internal/local sources run. Even when true, connectors stay read-only
    # and only run through an explicit operator request.
    enable_real_connectors: bool = Field(
        default=False,
        validation_alias=AliasChoices("FOUNDEROS_ENABLE_REAL_CONNECTORS"),
    )
    connector_network_timeout_seconds: int = Field(
        default=10,
        validation_alias=AliasChoices("FOUNDEROS_CONNECTOR_NETWORK_TIMEOUT_SECONDS"),
    )
    connector_sync_limit: int = Field(
        default=50,
        validation_alias=AliasChoices("FOUNDEROS_CONNECTOR_SYNC_LIMIT"),
    )
    connector_backfill_limit: int = Field(
        default=100,
        validation_alias=AliasChoices("FOUNDEROS_CONNECTOR_BACKFILL_LIMIT"),
    )
    connector_backfill_max_days: int = Field(
        default=30,
        validation_alias=AliasChoices("FOUNDEROS_CONNECTOR_BACKFILL_MAX_DAYS"),
    )
    # Explicit live scopes/allowlists. When required (default), a real
    # sync/backfill is blocked unless the source has an explicit scope, so a
    # whole Jira/GitHub org can never be read by accident. Names only; never
    # secrets.
    require_connector_scope: bool = Field(
        default=True,
        validation_alias=AliasChoices("FOUNDEROS_REQUIRE_CONNECTOR_SCOPE"),
    )
    jira_project_keys: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_JIRA_PROJECT_KEYS"),
    )
    github_repos: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_REPOS"),
    )

    api_auth_enabled: bool = False
    api_auth_key: SecretStr | str | None = None
    api_auth_header_name: str = "X-FounderOS-API-Key"

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "FOS_OPENAI_API_KEY"),
    )

    google_client_secrets_file: str = "./secrets/google_oauth_client.json"
    google_token_file: str = "./secrets/google_token.json"
    google_gmail_backfill_enabled: bool = False
    google_gmail_backfill_query: str | None = None
    google_drive_backfill_enabled: bool = False
    google_drive_ai_inbox_folder_id: str | None = None
    google_pubsub_topic: str | None = None
    google_pubsub_subscription: str | None = None
    google_gmail_token_file: str = "./secrets/google_gmail_token.json"

    email_me_addresses: str | None = None
    email_digest_show_low_priority: bool = False
    email_digest_show_marketing: bool = False
    email_digest_show_automated: bool = False
    email_digest_debug_triage: bool = False
    email_digest_debug_evidence: bool = False
    email_important_senders: str | None = None
    email_important_domains: str | None = None
    email_marketing_sender_blocklist: str | None = None
    email_important_project_keywords: str | None = None

    attention_triage_enabled: bool = False
    attention_triage_provider: str = "openai"
    attention_triage_model: str | None = None
    attention_triage_min_confidence_to_hide: float = 0.80
    attention_triage_review_threshold: float = 0.55
    attention_triage_max_text_chars: int = 6000
    digest_show_hidden: bool = False
    digest_debug_triage: bool = False
    digest_debug_evidence: bool = False

    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None

    github_webhook_secret: str | None = None
    gitlab_webhook_secret: str | None = None
    bitbucket_webhook_secret: str | None = None

    telegram_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "FOS_TELEGRAM_BOT_TOKEN"),
    )
    telegram_chat_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_CHAT_ID", "FOS_TELEGRAM_CHAT_ID"),
    )
    telegram_webhook_secret_token: str | None = None

    obsidian_vault_path: str = "./obsidian_vault"

    model_config = SettingsConfigDict(
        # Priority (highest first): real env vars > .env.local > .env > defaults.
        # pydantic-settings loads listed files in order, later overriding
        # earlier; a missing file is skipped. .env.local stays out of git.
        env_file=(".env", ".env.local"),
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
