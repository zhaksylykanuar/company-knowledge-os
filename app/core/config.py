import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_CORS_ALLOWED_ORIGINS = ("http://127.0.0.1:3000",)
DOTENV_DISABLE_ENV = "FOUNDEROS_DISABLE_DOTENV"
TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _settings_env_files() -> str | None:
    if os.environ.get(DOTENV_DISABLE_ENV, "").strip().casefold() in TRUE_ENV_VALUES:
        return None
    return ".env.local"


def _default_local_workspace_path() -> str:
    return str(Path(__file__).resolve().parents[2] / ".local")


def _split_csv_config(value: str | None) -> list[str]:
    if value is None:
        return []
    return [
        item.strip()
        for chunk in value.replace("\n", ",").split(",")
        for item in [chunk.strip()]
        if item
    ]


def _normalize_cors_origin(value: str) -> str | None:
    origin = value.strip().rstrip("/")
    if not origin or origin == "*":
        return None
    if not (origin.startswith("http://") or origin.startswith("https://")):
        return None
    return origin


def resolved_cors_allowed_origins(config: "Settings") -> list[str]:
    configured = [
        normalized
        for item in _split_csv_config(config.cors_allowed_origins)
        for normalized in [_normalize_cors_origin(item)]
        if normalized is not None
    ]
    if configured:
        return configured

    if config.app_env.strip().casefold() == "local":
        return list(LOCAL_CORS_ALLOWED_ORIGINS)
    return []


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "company-knowledge-os"
    api_base_url: str = "http://localhost:8000"
    # Minimum level for the application's basic request logger (MVP §1.5
    # "basic logging"). Standard Python level name; invalid values fall back to
    # INFO. The logger only records method, sanitized path, status, and duration
    # — never secrets, query values, headers, or request/response bodies.
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("FOUNDEROS_LOG_LEVEL", "LOG_LEVEL"),
    )
    readiness_database_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        le=10,
        validation_alias=AliasChoices(
            "FOUNDEROS_READINESS_DATABASE_TIMEOUT_SECONDS"
        ),
    )

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

    enable_llm: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_LLM", "FOUNDEROS_ENABLE_LLM"),
    )
    enable_write_actions: bool = False
    github_write_allowed_repos: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FOS_GITHUB_WRITE_ALLOWED_REPOS",
            "FOS_GITHUB_SMOKE_REPO",
        ),
    )
    github_sync_allowed_repos: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOS_GITHUB_SYNC_ALLOWED_REPOS"),
    )
    github_sync_worker_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_SYNC_WORKER_ENABLED"),
    )
    github_sync_worker_concurrency: int = Field(
        default=2,
        ge=1,
        le=4,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_SYNC_WORKER_CONCURRENCY"),
    )
    github_sync_worker_poll_seconds: float = Field(
        default=1.0,
        gt=0,
        le=30,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_SYNC_WORKER_POLL_SECONDS"),
    )
    github_sync_job_lease_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_SYNC_JOB_LEASE_SECONDS"),
    )
    github_sync_job_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_SYNC_JOB_MAX_ATTEMPTS"),
    )
    github_sync_job_retry_base_seconds: int = Field(
        default=5,
        ge=1,
        le=300,
        validation_alias=AliasChoices("FOUNDEROS_GITHUB_SYNC_JOB_RETRY_BASE_SECONDS"),
    )
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

    # --- Real connector network execution (opt-in; default OFF) ---
    # When false, real Jira/GitHub clients never make a network call; only
    # internal/local sources run. Enabling this gate permits provider network
    # access only. Provider writes additionally require ENABLE_WRITE_ACTIONS,
    # the approval/evidence/idempotency policy, and an explicit bounded request.
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
    secret_encryption_key: SecretStr | str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_SECRET_ENCRYPTION_KEY"),
    )
    api_auth_header_name: str = "X-FounderOS-API-Key"

    # --- Email+password server-side sessions ---
    # Session lifetime and non-secret cookie metadata. The cookie Secure flag is
    # derived from APP_ENV at response time (Secure outside local-like envs).
    session_ttl_days: int = Field(
        default=14,
        validation_alias=AliasChoices("FOUNDEROS_SESSION_TTL_DAYS"),
    )
    session_cookie_name: str = Field(
        default="founderos_session",
        validation_alias=AliasChoices("FOUNDEROS_SESSION_COOKIE_NAME"),
    )
    session_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        validation_alias=AliasChoices("FOUNDEROS_SESSION_COOKIE_SAMESITE"),
    )
    session_last_seen_interval_seconds: int = Field(
        default=300,
        ge=1,
        validation_alias=AliasChoices(
            "FOUNDEROS_SESSION_LAST_SEEN_INTERVAL_SECONDS"
        ),
    )
    # Login brute-force throttle: lock an email after N consecutive failures
    # for a cooldown window. DB-backed (login_attempts).
    login_max_failed_attempts: int = Field(
        default=5,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_MAX_FAILED_ATTEMPTS"),
    )
    login_lockout_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_LOCKOUT_MINUTES"),
    )
    # Production admission control runs before Argon2. Defaults fit the current
    # single-process private-beta deployment; multi-process deployments require
    # a shared edge/Redis limiter in addition to these process-local bounds.
    login_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_RATE_LIMIT_WINDOW_SECONDS"),
    )
    login_rate_limit_per_ip: int = Field(
        default=20,
        ge=1,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_RATE_LIMIT_PER_IP"),
    )
    login_rate_limit_global: int = Field(
        default=100,
        ge=1,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_RATE_LIMIT_GLOBAL"),
    )
    login_max_concurrent_attempts: int = Field(
        default=4,
        ge=1,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_MAX_CONCURRENT_ATTEMPTS"),
    )
    login_rate_limit_backend: Literal["process", "redis"] = Field(
        default="process",
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_RATE_LIMIT_BACKEND"),
    )
    login_rate_limit_redis_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        le=5,
        validation_alias=AliasChoices(
            "FOUNDEROS_LOGIN_RATE_LIMIT_REDIS_TIMEOUT_SECONDS"
        ),
    )
    trust_proxy_headers: bool = Field(
        default=False,
        validation_alias=AliasChoices("FOUNDEROS_TRUST_PROXY_HEADERS"),
    )
    trusted_proxy_cidrs: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FOUNDEROS_TRUSTED_PROXY_CIDRS"),
    )
    login_attempt_retention_hours: int = Field(
        default=24,
        ge=1,
        validation_alias=AliasChoices("FOUNDEROS_LOGIN_ATTEMPT_RETENTION_HOURS"),
    )
    auth_artifact_cleanup_interval_seconds: int = Field(
        default=3600,
        ge=60,
        validation_alias=AliasChoices(
            "FOUNDEROS_AUTH_ARTIFACT_CLEANUP_INTERVAL_SECONDS"
        ),
    )
    revoked_session_retention_hours: int = Field(
        default=24,
        ge=1,
        validation_alias=AliasChoices(
            "FOUNDEROS_REVOKED_SESSION_RETENTION_HOURS"
        ),
    )
    # Read-only assistant admission. The current runtime is one Uvicorn process;
    # any future multi-worker/public topology must replace this process-local
    # availability guard with a shared limiter.
    assistant_query_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "FOUNDEROS_ASSISTANT_QUERY_RATE_LIMIT_WINDOW_SECONDS"
        ),
    )
    assistant_query_rate_limit_per_user_workspace: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices(
            "FOUNDEROS_ASSISTANT_QUERY_RATE_LIMIT_PER_USER_WORKSPACE"
        ),
    )
    assistant_query_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        le=60,
        validation_alias=AliasChoices("FOUNDEROS_ASSISTANT_QUERY_TIMEOUT_SECONDS"),
    )
    assistant_llm_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        le=45,
        validation_alias=AliasChoices("FOUNDEROS_ASSISTANT_LLM_TIMEOUT_SECONDS"),
    )

    cors_allowed_origins: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FOUNDEROS_CORS_ALLOWED_ORIGINS",
            "CORS_ORIGINS",
        ),
    )
    cors_allow_credentials: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "FOUNDEROS_CORS_ALLOW_CREDENTIALS",
            "CORS_ALLOW_CREDENTIALS",
        ),
    )

    obsidian_vault_path: str = "./obsidian_vault"

    model_config = SettingsConfigDict(
        # Priority (highest first): real env vars > .env.local > defaults.
        # `.env.local` is the single canonical local runtime file and stays out
        # of git. The backend checker sets FOUNDEROS_DISABLE_DOTENV before this
        # module is imported, disabling the file for isolated commands.
        env_file=_settings_env_files(),
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
