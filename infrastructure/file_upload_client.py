from __future__ import annotations

import json
from pathlib import Path

import requests


class FileUploadError(Exception):
    """Raised when file upload fails."""


class FileUploadClient:
    """Uploads generated order files to a remote file server.

    The server stores files under a UUID-based filename and returns a
    public download URL that can be included in group text messages.
    """

    def __init__(self, api_url: str, timeout_seconds: float = 30) -> None:
        if not api_url.strip():
            raise ValueError("api_url must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")

        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def upload(self, file_path: str | Path) -> str:
        """Uploads a file and returns its public download URL."""
        path = Path(file_path)
        if not path.is_file():
            raise FileUploadError(f"File not found: {path}")

        try:
            resp = requests.post(
                self.api_url,
                files={"file": path.open("rb")},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise FileUploadError(f"Upload request failed: {exc}") from exc

        if resp.status_code != 200:
            raise FileUploadError(
                f"Upload failed: HTTP {resp.status_code}, body={resp.text}"
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise FileUploadError(
                f"Upload response is not valid JSON: {resp.text}"
            ) from exc

        url = data.get("url")
        if not isinstance(url, str) or not url.strip():
            raise FileUploadError(
                f"Upload response missing url field: {data}"
            )

        # 接口可能返回完整 URL 或相对路径，避免重复拼接域名
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"http://mengyang.renruikeji.cn{url}"
