"""Argon2id password hashing contract (no DB)."""

from __future__ import annotations

import pytest

from app.services.password_service import hash_password, verify_password


def test_hash_differs_from_plaintext_and_is_argon2id() -> None:
    plaintext = "correct horse battery staple"
    hashed = hash_password(plaintext)
    assert hashed != plaintext
    assert hashed.startswith("$argon2id$")  # Argon2id PHC string


def test_verify_correct_returns_true_and_wrong_returns_false() -> None:
    hashed = hash_password("s3cret-pw")
    assert verify_password("s3cret-pw", hashed) is True
    assert verify_password("wrong-pw", hashed) is False


def test_two_hashes_of_same_password_differ_due_to_salt() -> None:
    first = hash_password("same-pw")
    second = hash_password("same-pw")
    assert first != second
    # Both still verify — different salt, same password.
    assert verify_password("same-pw", first) is True
    assert verify_password("same-pw", second) is True


def test_stored_hash_does_not_contain_plaintext() -> None:
    plaintext = "unique-plaintext-marker-xyz"
    hashed = hash_password(plaintext)
    assert plaintext not in hashed


def test_verify_handles_missing_hash_and_empty_password() -> None:
    assert verify_password("pw", None) is False
    assert verify_password("", hash_password("pw")) is False


def test_hash_password_rejects_empty_plaintext() -> None:
    with pytest.raises(ValueError):
        hash_password("")
