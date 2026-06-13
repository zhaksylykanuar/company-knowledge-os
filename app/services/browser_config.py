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
