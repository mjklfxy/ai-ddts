from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from infrastructure.message_adapter import MessagePayload


class QixinApiError(Exception):
    """Raised when the Qixin API returns a business or system error."""


def _canonical_json(body: str) -> str:
    """Re-serialises JSON with sorted keys and no whitespace for signing."""
    return json.dumps(
        json.loads(body),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _build_sign(
    caller_id: str,
    timestamp: str,
    canonical_query: str,
    canonical_body: str,
    secret_key: str,
) -> str:
    """Builds HMAC-SHA256 sign using URL-encoded parameter signing.

    signContent = "callerId=URLEncode(callerId)&timestamp=URLEncode(timestamp)
                   &canonicalQuery=URLEncode(canonicalQuery)
                   &canonicalBody=URLEncode(canonicalBody)"
    """
    sign_content = (
        f"callerId={urllib.parse.quote(caller_id, safe='')}"
        f"&timestamp={urllib.parse.quote(timestamp, safe='')}"
        f"&canonicalQuery={urllib.parse.quote(canonical_query, safe='')}"
        f"&canonicalBody={urllib.parse.quote(canonical_body, safe='')}"
    )
    return hmac.new(
        secret_key.encode("utf-8"),
        sign_content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class QixinClient:
    """Low-level HTTP client for the Qixin group message API.

    Handles HMAC-SHA256 signing, request serialisation, and response parsing.
    """

    SEND_TEXT_PATH = "/agent/auth/message/sendTextToGroup"
    SEND_FILE_PATH = "/agent/auth/message/sendFileToGroup"

    def __init__(
        self,
        api_base_url: str,
        caller_id: str,
        secret_key: str,
        timeout_seconds: float = 30,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        if not api_base_url.strip():
            raise ValueError("api_base_url must be a non-empty string")
        if not caller_id.strip():
            raise ValueError("caller_id must be a non-empty string")
        if not secret_key.strip():
            raise ValueError("secret_key must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")

        base = api_base_url.rstrip("/")
        self.send_text_url = f"{base}{self.SEND_TEXT_PATH}"
        self.send_file_url = f"{base}{self.SEND_FILE_PATH}"
        self.caller_id = caller_id.strip()
        self.secret_key = secret_key.strip()
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen or urllib.request.urlopen

    def send_text(self, group_name: str, content: str, user_id: str) -> str:
        """Sends a text message to a Qixin group and returns the messageId."""

        raw_body = json.dumps(
            {
                "userId": user_id,
                "groupName": group_name,
                "content": content,
            },
            ensure_ascii=False,
        )

        canonical_body = _canonical_json(raw_body)
        timestamp = str(int(time.time()))
        sign = _build_sign(
            caller_id=self.caller_id,
            timestamp=timestamp,
            canonical_query="",
            canonical_body=canonical_body,
            secret_key=self.secret_key,
        )

        http_request = urllib.request.Request(
            self.send_text_url,
            data=raw_body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "callerId": self.caller_id,
                "timestamp": timestamp,
                "sign": sign,
            },
            method="POST",
        )

        try:
            response = self.urlopen(http_request, timeout=self.timeout_seconds)
            try:
                raw_body = response.read()
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except urllib.error.URLError as exc:
            raise QixinApiError(
                f"Qixin request failed: {exc.__class__.__name__}"
            ) from exc

        payload = _decode_response(raw_body)
        return _extract_message_id(payload)


    def send_file_to_group(
        self, group_name: str, file_url: str, file_name: str, user_id: str
    ) -> str:
        """Sends a file message to a Qixin group and returns the messageId."""

        raw_body = json.dumps(
            {
                "userId": user_id,
                "groupName": group_name,
                "fileUrl": file_url,
                "fileName": file_name,
            },
            ensure_ascii=False,
        )

        canonical_body = _canonical_json(raw_body)
        timestamp = str(int(time.time()))
        sign = _build_sign(
            caller_id=self.caller_id,
            timestamp=timestamp,
            canonical_query="",
            canonical_body=canonical_body,
            secret_key=self.secret_key,
        )

        http_request = urllib.request.Request(
            self.send_file_url,
            data=raw_body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "callerId": self.caller_id,
                "timestamp": timestamp,
                "sign": sign,
            },
            method="POST",
        )

        try:
            response = self.urlopen(http_request, timeout=self.timeout_seconds)
            try:
                raw_body = response.read()
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except urllib.error.URLError as exc:
            raise QixinApiError(
                f"Qixin request failed: {exc.__class__.__name__}"
            ) from exc

        payload = _decode_response(raw_body)
        return _extract_message_id(payload)


def _decode_response(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        raise QixinApiError("Qixin response body is empty")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise QixinApiError("Qixin response must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise QixinApiError("Qixin response must be a JSON object")
    return payload


def _extract_message_id(payload: dict[str, Any]) -> str:
    code = payload.get("code")
    # API 用 code=0 且 message="操作成功" 表示成功
    if code in (0, 200):
        pass  # success
    else:
        message = payload.get("message") or "unknown error"
        raise QixinApiError(f"Qixin API system error: code={code}, message={message}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise QixinApiError("Qixin response missing data field")

    message_id = data.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip():
        raise QixinApiError("Qixin response missing messageId")

    return message_id


ContentBuilder = Callable[[MessagePayload], str]
# === MODIFIED START ===
# 原因：推送/上传文件统一改为 Excel，消息内容没有 file_path 时也应使用 xlsx 兜底名。
# 影响范围：祺信文本链接、上传链接、文件直推默认文件名。
DEFAULT_ORDER_FILE_NAME = "orders.xlsx"
# === MODIFIED END ===


def build_download_url(base_url: str, filename: str, secret_key: str) -> str:
    """Returns a signed download URL for a single order file."""
    sig = hmac.HMAC(
        secret_key.encode("utf-8"),
        filename.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    params = urllib.parse.urlencode({"filename": filename, "sig": sig})
    return f"{base_url.rstrip('/')}/order-files/download?{params}"


def make_link_content_builder(base_url: str, secret_key: str) -> ContentBuilder:
    """Returns a content builder that embeds a signed download link."""

    def _build(payload: MessagePayload) -> str:
        file_name = payload.file_path.name if payload.file_path else DEFAULT_ORDER_FILE_NAME
        url = build_download_url(base_url, file_name, secret_key)
        return f"订单文件已生成：{file_name}\n下载链接：{url}\n请及时处理。"

    return _build


def make_upload_content_builder() -> ContentBuilder:
    """Returns a content builder that uses a pre-uploaded file URL."""

    def _build(payload: MessagePayload) -> str:
        file_name = payload.file_path.name if payload.file_path else DEFAULT_ORDER_FILE_NAME
        url = payload.file_url or ""
        return f"订单文件已生成：{file_name}\n下载链接：{url}\n请及时处理。"

    return _build


def _default_content(payload: MessagePayload) -> str:
    file_name = payload.file_path.name if payload.file_path else DEFAULT_ORDER_FILE_NAME
    return f"订单文件已生成：{file_name}\n请及时处理。"


class QixinSender:
    """Adapts MessagePayload to QixinClient, implementing the Sender protocol.

    Can be used directly as the ``sender`` argument to ``MessageAdapter``.
    Supports two push modes:

    - ``"link"`` (default): sends a text message with a signed download link.
    - ``"file"``: sends a file message directly via sendFileToGroup API.
    """

    def __init__(
        self,
        client: QixinClient,
        content_builder: ContentBuilder | None = None,
        # === MODIFIED START ===
        # 原因：消息推送需要支持"文本链接推送"和"文件直推"两种模式。
        # 影响范围：QixinSender 推送逻辑、Pipeline MessagePayload 构建。
        push_mode: str = "link",
        # === MODIFIED END ===
    ) -> None:
        self.client = client
        self.content_builder = content_builder or _default_content
        # === MODIFIED START ===
        # 原因：支持"文本链接推送"和"文件直推"两种模式切换。
        # 影响范围：QixinSender.send_file 推送逻辑。
        self.push_mode = push_mode
        # === MODIFIED END ===

    def __call__(self, payload: MessagePayload) -> str:
        """Sends one file notification and returns the Qixin messageId as tracking id."""
        return self.send_file(payload)

    def send_file(self, payload: MessagePayload) -> str:
        """Sends a file notification using the configured push mode."""
        if self.push_mode == "file":
            return self._send_file_message(payload)
        return self._send_link_message(payload)

    def _send_link_message(self, payload: MessagePayload) -> str:
        """Sends a text message with a signed download link."""
        content = self.content_builder(payload)
        return self.client.send_text(
            group_name=payload.group_name,
            content=content,
            user_id=payload.user_id,
        )

    def _send_file_message(self, payload: MessagePayload) -> str:
        """Sends a file message directly to the group."""
        if not payload.file_url:
            raise QixinApiError(
                "file push mode requires a file_url on MessagePayload; "
                "set download.base_url and DOWNLOAD_SECRET_KEY in config"
            )
        file_name = payload.file_path.name if payload.file_path else DEFAULT_ORDER_FILE_NAME
        return self.client.send_file_to_group(
            group_name=payload.group_name,
            file_url=payload.file_url,
            file_name=file_name,
            user_id=payload.user_id,
        )


class RemoteUserResolverError(Exception):
    """Raised when the remote userid API returns an error."""


class RemoteUserResolver:
    """Resolves enterprise WeChat userids from phone numbers via a remote proxy API."""

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

        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen or urllib.request.urlopen

    def get_userid_by_mobile(self, mobile: str) -> str:
        """Returns the enterprise WeChat userid for the given phone number."""
        if not mobile or not mobile.strip():
            raise ValueError("mobile must be a non-empty string")

        body = json.dumps({"mobile": mobile.strip()}).encode("utf-8")
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
            raise RemoteUserResolverError(
                f"userid API request failed: {exc.__class__.__name__}"
            ) from exc

        if not raw_body:
            raise RemoteUserResolverError("userid API response body is empty")
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RemoteUserResolverError("userid API response must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteUserResolverError("userid API response must be a JSON object")

        userid = payload.get("userid")
        if not isinstance(userid, str) or not userid.strip():
            raise RemoteUserResolverError(
                f"userid API response missing userid: {payload}"
            )
        return userid.strip()
