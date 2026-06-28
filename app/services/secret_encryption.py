from __future__ import annotations

from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core.config import settings

ENCRYPTED_SECRET_PREFIX = "fernet:v1:"

# APP_ENV values where reusing the API auth key as encryption-key material is
# tolerated as a clearly-marked developer convenience. Mirrors the auth
# fail-closed policy (app/api/auth.py LOCAL_LIKE_APP_ENVS); kept local to avoid
# a services -> api import.
_LOCAL_LIKE_APP_ENVS = frozenset({"local", "dev", "development", "test", "testing"})


class SecretEncryptionConfig(Protocol):
    secret_encryption_key: SecretStr | str | None
    api_auth_key: SecretStr | str | None
    app_env: str


class SecretEncryptionError(RuntimeError):
    pass


def encrypt_secret(value: str, *, config: SecretEncryptionConfig = settings) -> str:
    plaintext = value.strip()
    if not plaintext:
        raise SecretEncryptionError("secret value must not be empty")
    token = _fernet(config).encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_SECRET_PREFIX}{token}"


def decrypt_secret(value: str, *, config: SecretEncryptionConfig = settings) -> str:
    if not value.startswith(ENCRYPTED_SECRET_PREFIX):
        raise SecretEncryptionError("unsupported encrypted secret format")
    encrypted = value.removeprefix(ENCRYPTED_SECRET_PREFIX)
    try:
        return _fernet(config).decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretEncryptionError("encrypted secret could not be decrypted") from exc


def _fernet(config: SecretEncryptionConfig) -> Fernet:
    key_material = _configured_key_material(config)
    digest = sha256(f"founderos-fernet-v1:{key_material}".encode("utf-8")).digest()
    return Fernet(urlsafe_b64encode(digest))


def _is_local_like_env(config: SecretEncryptionConfig) -> bool:
    app_env = getattr(config, "app_env", "") or ""
    if not isinstance(app_env, str):
        return False
    return app_env.strip().casefold() in _LOCAL_LIKE_APP_ENVS


def _configured_key_material(config: SecretEncryptionConfig) -> str:
    explicit = _secret_value(config.secret_encryption_key)
    if explicit:
        return explicit
    # No dedicated encryption key. Fail closed outside local/dev rather than
    # silently reusing the API auth key as encryption material: rotating the
    # API key would otherwise make every stored provider token undecryptable,
    # and one leaked secret would compromise both boundaries.
    if not _is_local_like_env(config):
        raise SecretEncryptionError(
            "FOUNDEROS_SECRET_ENCRYPTION_KEY must be set outside local/dev; "
            "refusing to reuse the API auth key as encryption material."
        )
    # Local/dev only: tolerate reusing the API auth key as a dev convenience.
    api_key = _secret_value(config.api_auth_key)
    if api_key:
        return api_key
    raise SecretEncryptionError("secret encryption key is not configured")


def _secret_value(value: SecretStr | str | None) -> str | None:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
