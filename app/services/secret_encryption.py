from __future__ import annotations

from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core.config import settings

ENCRYPTED_SECRET_PREFIX = "fernet:v1:"


class SecretEncryptionConfig(Protocol):
    secret_encryption_key: SecretStr | str | None
    api_auth_key: SecretStr | str | None


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


def _configured_key_material(config: SecretEncryptionConfig) -> str:
    explicit = _secret_value(config.secret_encryption_key)
    if explicit:
        return explicit
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
