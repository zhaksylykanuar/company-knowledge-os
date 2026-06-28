"""Argon2id password hashing for email+password auth (Chunk 1 core).

Plaintext passwords are never stored or logged: callers persist only the value
returned by :func:`hash_password`, and verification is delegated to argon2-cffi's
constant-time verify. Each hash embeds a random salt, so two hashes of the same
password differ.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

# Defaults select Argon2id with library-recommended cost parameters.
_hasher = PasswordHasher()


def hash_password(plaintext: str) -> str:
    """Return an Argon2id hash (with embedded salt + parameters) for ``plaintext``."""

    if not isinstance(plaintext, str) or plaintext == "":
        raise ValueError("password must be a non-empty string")
    return _hasher.hash(plaintext)


def verify_password(plaintext: str, stored_hash: str | None) -> bool:
    """Constant-time verify of ``plaintext`` against ``stored_hash``.

    Returns False (never raises) for a wrong password, a missing hash, or a
    user that has no password set yet. Never compares plaintext with ``==``.
    """

    if not plaintext or not stored_hash:
        return False
    try:
        return _hasher.verify(stored_hash, plaintext)
    except Argon2Error:
        return False
