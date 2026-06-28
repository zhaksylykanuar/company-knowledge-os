"""Fail-closed encryption-key policy for secret_encryption.

Outside local/dev a dedicated FOUNDEROS_SECRET_ENCRYPTION_KEY is required; the
module must never silently reuse the API auth key as encryption material in a
hosted environment. No real key material is used here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.secret_encryption import (
    SecretEncryptionError,
    decrypt_secret,
    encrypt_secret,
)


def _config(*, app_env: str, secret_encryption_key, api_auth_key):
    return SimpleNamespace(
        app_env=app_env,
        secret_encryption_key=secret_encryption_key,
        api_auth_key=api_auth_key,
    )


def test_encryption_fails_closed_outside_local_without_dedicated_key() -> None:
    config = _config(
        app_env="production",
        secret_encryption_key=None,
        api_auth_key="operator-api-key",  # present, but must NOT be reused
    )

    with pytest.raises(SecretEncryptionError) as exc_info:
        encrypt_secret("provider-token-value", config=config)

    message = str(exc_info.value)
    assert "FOUNDEROS_SECRET_ENCRYPTION_KEY" in message
    # The error names the variable, never any key material.
    assert "operator-api-key" not in message


def test_encryption_roundtrips_outside_local_with_dedicated_key() -> None:
    config = _config(
        app_env="production",
        secret_encryption_key="dedicated-encryption-key",
        api_auth_key=None,
    )

    encrypted = encrypt_secret("provider-token-value", config=config)
    assert encrypted.startswith("fernet:v1:")
    assert decrypt_secret(encrypted, config=config) == "provider-token-value"


def test_local_dev_may_reuse_api_auth_key_fallback() -> None:
    # Developer convenience: local/dev without a dedicated key still works by
    # reusing the API auth key as material.
    config = _config(
        app_env="local",
        secret_encryption_key=None,
        api_auth_key="dev-operator-key",
    )

    encrypted = encrypt_secret("provider-token-value", config=config)
    assert decrypt_secret(encrypted, config=config) == "provider-token-value"
