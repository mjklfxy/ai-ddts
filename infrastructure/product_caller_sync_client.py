from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


class ProductCallerConfigSyncError(Exception):
    """Raised when product caller config sync fails."""


class ProductCallerConfigSyncClient:
    """HTTP client for push-center product caller config synchronization."""

    def __init__(
        self,
        api_url: str,
        timeout_seconds: float = 30,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        if not api_url.strip():
            raise ValueError("api_url must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")

        self.api_url = api_url.strip()
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen or urllib.request.urlopen

    def sync(self, data_id: int, data: list[dict[str, str]]) -> dict[str, Any]:
        """Posts product caller config rows and returns the remote JSON response."""

        body = json.dumps(
            {
                "data_id": data_id,
                "count": len(data),
                "data": data,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            response = self.urlopen(request, timeout=self.timeout_seconds)
            try:
                raw_body = response.read()
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except urllib.error.URLError as exc:
            raise ProductCallerConfigSyncError(
                f"product caller sync request failed: {exc.__class__.__name__}"
            ) from exc

        payload = _decode_response(raw_body)
        code = payload.get("code")
        if code != 200:
            message = payload.get("message") or "unknown error"
            raise ProductCallerConfigSyncError(
                f"product caller sync failed: code={code}, message={message}"
            )
        return payload


def _decode_response(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        raise ProductCallerConfigSyncError("product caller sync response body is empty")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProductCallerConfigSyncError("product caller sync response must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProductCallerConfigSyncError("product caller sync response must be a JSON object")
    return payload
