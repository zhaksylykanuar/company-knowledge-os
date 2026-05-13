from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "company-knowledge-os"
    api_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://ckdos:ckdos_dev_password@localhost:5432/ckdos"
    redis_url: str = "redis://localhost:6379/0"

    raw_storage_dir: str = "./raw_storage"

    enable_llm: bool = False
    enable_write_actions: bool = False
    enable_obsidian_export: bool = True
    require_approval_for_writes: bool = True

    api_auth_enabled: bool = False
    api_auth_key: SecretStr | str | None = None
    api_auth_header_name: str = "X-FounderOS-API-Key"

    openai_api_key: str | None = None

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

    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None

    github_webhook_secret: str | None = None
    gitlab_webhook_secret: str | None = None
    bitbucket_webhook_secret: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_webhook_secret_token: str | None = None

    obsidian_vault_path: str = "./obsidian_vault"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
