from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import sleep


@dataclass(frozen=True, slots=True)
class MessagePayload:
    """Message file payload sent to an external group channel."""

    trace_id: str
    group_name: str
    owner_mobile: str
    user_id: str
    file_path: Path
    # === MODIFIED START ===
    # 原因：祺信文件直推模式需要知道文件的公网下载地址。
    # 影响范围：MessagePayload、QixinSender 文件直推、MessageAdapter。
    file_url: str | None = None
    # === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class MessageSendResult:
    """Result returned after a message file is sent successfully."""

    trace_id: str
    group_name: str
    tracking_id: str
    attempts: int


class MessageSendError(Exception):
    """Raised when a message file cannot be sent after retries."""


Sender = Callable[[MessagePayload], str]
LogInfo = Callable[[str, dict[str, object]], None]
LogError = Callable[[str, dict[str, object]], None]
Sleeper = Callable[[float], None]


class MessageAdapter:
    """Sends group file messages with retry support."""

    def __init__(
        self,
        sender: Sender,
        max_attempts: int = 3,
        retry_interval_seconds: float = 0,
        log_info: LogInfo | None = None,
        log_error: LogError | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be greater than or equal to 1")

        self.sender = sender
        self.max_attempts = max_attempts
        self.retry_interval_seconds = retry_interval_seconds
        self.log_info = log_info or self._noop_log
        self.log_error = log_error or self._noop_log
        self.sleeper = sleeper or sleep

    def send_file(self, payload: MessagePayload) -> MessageSendResult:
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                tracking_id = self.sender(payload)
            except Exception as exc:
                last_error = exc
                self.log_error(
                    "message_send_failed",
                    {
                        "trace_id": payload.trace_id,
                        "group_id": payload.group_name,
                        "attempt": attempt,
                        "max_attempts": self.max_attempts,
                        "error": str(exc),
                    },
                )
                if attempt < self.max_attempts and self.retry_interval_seconds > 0:
                    self.sleeper(self.retry_interval_seconds)
                continue

            self.log_info(
                "message_send_success",
                {
                    "trace_id": payload.trace_id,
                    "group_id": payload.group_name,
                    "attempt": attempt,
                    "tracking_id": tracking_id,
                },
            )
            return MessageSendResult(
                trace_id=payload.trace_id,
                group_name=payload.group_name,
                tracking_id=tracking_id,
                attempts=attempt,
            )

        raise MessageSendError(
            f"Message send failed after {self.max_attempts} attempts: {last_error}"
        )

    @staticmethod
    def _noop_log(event: str, payload: dict[str, object]) -> None:
        _ = (event, payload)
