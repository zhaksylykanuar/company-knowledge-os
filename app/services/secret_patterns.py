"""Detection of secret *values* (not names) in generated, founder-facing text.

Connector diagnostics and Obsidian connector notes intentionally include
environment-variable *names* (e.g. ``GITHUB_TOKEN``) so the founder can see
what is missing. Those names are not secrets. What must never appear is a
secret *value* (a real token/key) or a ``NAME=value`` assignment carrying one.

This module flags values, not names, so it can guard generated output without
redacting the legitimate variable names the setup wizard needs to show.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

# Real secret value shapes (provider tokens, private keys, JWTs, raw refs).
SECRET_VALUE_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|gho_[A-Za-z0-9]{20,}"
    r"|ghu_[A-Za-z0-9]{20,}"
    r"|ghs_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{16,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{12,}"
    r"|ya29\.[A-Za-z0-9_-]{10,}"
    r"|-----BEGIN[A-Z ]*PRIVATE KEY-----"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"
    r"|raw://\S+"
)

# A NAME=value / NAME: value assignment where the NAME looks credential-bearing.
ENV_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z][A-Z0-9_]{2,}(?:TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL))\s*[=:]\s*(\S+)"
)

_PLACEHOLDER_VALUES = {
    "",
    "configured",
    "false",
    "masked",
    "masked_or_missing",
    "missing",
    "none",
    "not_required",
    "null",
    "partial",
    "ready",
    "true",
}


def _is_placeholder_value(value: str) -> bool:
    text = value.strip().strip('"').strip("'").casefold()
    if not text or text in _PLACEHOLDER_VALUES:
        return True
    if "redact" in text or "mask" in text:
        return True
    return text.startswith("<") and text.endswith(">")


def contains_secret_value(text: str) -> bool:
    if not isinstance(text, str):
        return False
    if SECRET_VALUE_RE.search(text):
        return True
    for match in ENV_ASSIGNMENT_RE.finditer(text):
        if not _is_placeholder_value(match.group(2)):
            return True
    return False


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def assert_no_secret_values(value: Any) -> None:
    """Raise ``ValueError`` if any string anywhere in ``value`` holds a secret."""

    for text in _iter_strings(value):
        if contains_secret_value(text):
            raise ValueError("secret_value_detected")
