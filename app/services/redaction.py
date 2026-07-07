"""Deterministic redaction helpers for reports and API payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "card_number",
        "cookie",
        "cvv",
        "password",
        "secret",
        "secret_name",
        "sentry_key",
        "sentry_secret",
        "token",
    }
)
REDACTED = "[REDACTED]"
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_ASSIGNMENT_RE = re.compile(
    r"\b(api[_-]?key|authorization|dsn|password|secret|sentry[_-]?key|sentry[_-]?secret|[a-z0-9_-]*token)=([^\s,;]+)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: REDACTED if _is_sensitive_key(str(key)) else redact_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value


def redact_text(text: str) -> str:
    redacted = _BEARER_RE.sub("Bearer " + REDACTED, text)
    redacted = _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", redacted)
    return _EMAIL_RE.sub(REDACTED, redacted)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or normalized.endswith(("_key", "_token", "_secret", "_password"))
