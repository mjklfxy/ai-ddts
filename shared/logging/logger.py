from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "app_secret",
        "appsecret",
        "appSecret",
        "APP_SECRET",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "sign",
        "password",
        "密钥",
    }
)


def log_info(event: str, payload: Mapping[str, Any]) -> None:
    """Logs an info event with required trace id and redacted payload."""

    _log(logging.INFO, event, payload)


def log_error(event: str, payload: Mapping[str, Any]) -> None:
    """Logs an error event with required trace id and redacted payload."""

    _log(logging.ERROR, event, payload)


def sanitize_payload(payload: Any) -> Any:
    """Recursively redacts sensitive values in log payloads."""

    if isinstance(payload, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(str(key)) else sanitize_payload(value)
            for key, value in payload.items()
        }

    if isinstance(payload, list):
        return [sanitize_payload(value) for value in payload]

    if isinstance(payload, tuple):
        return tuple(sanitize_payload(value) for value in payload)

    return payload


def _log(level: int, event: str, payload: Mapping[str, Any]) -> None:
    if "trace_id" not in payload or not payload["trace_id"]:
        raise ValueError("log payload must include trace_id")

    sanitized_payload = sanitize_payload(dict(payload))
    logging.getLogger("ai_ddts").log(
        level,
        json.dumps(
            {
                "event": event,
                "payload": sanitized_payload,
            },
            ensure_ascii=False,
            default=str,
        ),
    )


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.lower()
    return key in SENSITIVE_KEYS or normalized_key in SENSITIVE_KEYS
