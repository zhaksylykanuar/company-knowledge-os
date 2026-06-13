"""Safe browser dev config — the ONLY config the backend hands to a browser.

The browser may receive a local dev API key (for the LOCAL backend only),
the base URL and feature flags. It must NEVER receive external/third-party
secrets (OpenAI / GitHub / Jira / Gmail / OAuth / connector credentials).
``sanitize_browser_config`` constructs the payload from an explicit
allowlist — it never iterates settings — so a new secret field added to
settings can never accidentally leak here.
"""

from __future__ import annotations

from typing import Any, Protocol

# Feature flags safe to expose to the browser in local dev.
SAFE_FEATURES: dict[str, bool] = {
    "share_packs": True,
    "role_views": True,
    "source_explorer": True,
}

# The exhaustive allowlist of keys the browser config may ever contain.
ALLOWED_KEYS = ("api_base_url", "dev_api_key", "app_env", "features")
_MASKED = "***redacted***"
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
)


class BrowserConfigSource(Protocol):
    app_env: str
    founderos_api_base_url: str
    dev_api_key: str | None
    enable_browser_dev_config: bool


def browser_dev_config_enabled(config: Any) -> bool:
    """The dev config endpoint is available only in local with the flag on."""

    return (
        getattr(config, "app_env", None) == "local"
        and bool(getattr(config, "enable_browser_dev_config", False))
    )


def sanitize_browser_config(config: Any) -> dict[str, Any]:
    """Build the browser payload from an explicit allowlist of safe fields.

    Never reads OpenAI/GitHub/Jira/Gmail/OAuth/connector settings; only the
    base URL, the local dev key, app_env and feature flags.
    """

    dev_key = getattr(config, "dev_api_key", None)
    payload = {
        "api_base_url": str(getattr(config, "founderos_api_base_url", "") or ""),
        "dev_api_key": dev_key if isinstance(dev_key, str) else "",
        "app_env": str(getattr(config, "app_env", "") or ""),
        "features": dict(SAFE_FEATURES),
    }
    # Defensive: guarantee the payload only ever carries allowlisted keys.
    return {key: payload[key] for key in ALLOWED_KEYS}


def sanitize_for_logs(value: Any) -> Any:
    """Return a log-safe copy of config-like values.

    The browser config may legitimately contain ``dev_api_key`` for local
    bootstrap, but logs must never include it. This helper is recursive so it
    also protects future config dumps without having to enumerate every shape.
    """

    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).casefold()
            if any(part in key_text for part in _SENSITIVE_KEY_PARTS):
                safe[str(key)] = _MASKED if item not in (None, "") else item
            else:
                safe[str(key)] = sanitize_for_logs(item)
        return safe
    if isinstance(value, list):
        return [sanitize_for_logs(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_logs(item) for item in value)
    if hasattr(value, "model_dump"):
        return sanitize_for_logs(value.model_dump())
    return value


def redact_config_for_logs(config: Any) -> dict[str, Any]:
    """Log-safe settings/config representation with sensitive values masked."""

    if isinstance(config, dict):
        raw = config
    elif hasattr(config, "model_dump"):
        raw = config.model_dump()
    else:
        raw = {
            key: getattr(config, key)
            for key in dir(config)
            if not key.startswith("_") and not callable(getattr(config, key, None))
        }
    safe = sanitize_for_logs(raw)
    return safe if isinstance(safe, dict) else {}
