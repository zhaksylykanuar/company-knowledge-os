from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "company-knowledge-os"
    api_base_url: str = "http://localhost:8000"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    raw_storage_dir: str = "./raw_storage"

    enable_llm: bool = False
    enable_write_actions: bool = False
    enable_obsidian_export: bool = True
    require_approval_for_writes: bool = True

    openai_api_key: str | None = None

    google_client_secrets_file: str = "./secrets/google_oauth_client.json"
    google_token_file: str = "./secrets/google_token.json"

    obsidian_vault_path: str = "./obsidian_vault"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()