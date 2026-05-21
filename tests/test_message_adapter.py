from pathlib import Path
from unittest import TestCase

from infrastructure.message_adapter import (
    MessageAdapter,
    MessagePayload,
    MessageSendError,
    MessageSendResult,
)


class MessageAdapterTests(TestCase):
    """Tests message sending retry behavior."""

    def test_send_file_success_returns_tracking_result(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        adapter = MessageAdapter(
            sender=lambda payload: f"TRACK-{payload.group_name}",
            log_info=lambda event, payload: logs.append((event, payload)),
        )

        result = adapter.send_file(
            MessagePayload(
                trace_id="TRACE-001",
                group_name="GROUP-A",
                owner_mobile="",
                user_id="",
                file_path=Path("outputs/GROUP-A.csv"),
            )
        )

        self.assertIsInstance(result, MessageSendResult)
        self.assertEqual(result.tracking_id, "TRACK-GROUP-A")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(logs[0][0], "message_send_success")
        self.assertEqual(logs[0][1]["trace_id"], "TRACE-001")

    def test_send_file_retries_until_success(self) -> None:
        attempts: list[int] = []
        error_logs: list[tuple[str, dict[str, object]]] = []
        info_logs: list[tuple[str, dict[str, object]]] = []

        def sender(payload: MessagePayload) -> str:
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("temporary failure")
            return "TRACK-OK"

        adapter = MessageAdapter(
            sender=sender,
            max_attempts=3,
            log_info=lambda event, payload: info_logs.append((event, payload)),
            log_error=lambda event, payload: error_logs.append((event, payload)),
        )

        result = adapter.send_file(
            MessagePayload(
                trace_id="TRACE-001",
                group_name="GROUP-A",
                owner_mobile="",
                user_id="",
                file_path=Path("outputs/GROUP-A.csv"),
            )
        )

        self.assertEqual(result.tracking_id, "TRACK-OK")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(error_logs), 2)
        self.assertEqual(error_logs[0][0], "message_send_failed")
        self.assertEqual(info_logs[0][0], "message_send_success")

    def test_send_file_raises_after_all_retries_fail(self) -> None:
        error_logs: list[tuple[str, dict[str, object]]] = []
        adapter = MessageAdapter(
            sender=lambda payload: (_ for _ in ()).throw(RuntimeError("down")),
            max_attempts=2,
            log_error=lambda event, payload: error_logs.append((event, payload)),
        )

        with self.assertRaises(MessageSendError):
            adapter.send_file(
                MessagePayload(
                    trace_id="TRACE-001",
                    group_name="GROUP-A",
                    owner_mobile="",
                    user_id="",
                    file_path=Path("outputs/GROUP-A.csv"),
                )
            )

        self.assertEqual(len(error_logs), 2)
        self.assertEqual(error_logs[0][1]["trace_id"], "TRACE-001")

    def test_invalid_max_attempts_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_attempts"):
            MessageAdapter(
                sender=lambda payload: "TRACK-OK",
                max_attempts=0,
            )
