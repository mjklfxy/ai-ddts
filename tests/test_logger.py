import json
import logging
from unittest import TestCase

from shared.logging.logger import REDACTED, _get_project_logger, log_error, log_info, sanitize_payload


class ListLogHandler(logging.Handler):
    """Collects emitted logging records for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class LoggerTests(TestCase):
    """Tests shared logging redaction and trace id enforcement."""

    def test_sanitize_payload_redacts_sensitive_keys_recursively(self) -> None:
        payload = {
            "trace_id": "TRACE-001",
            "app_secret": "secret-value",
            "nested": {
                "token": "token-value",
                "safe": "ok",
            },
            "items": [
                {"sign": "sign-value"},
            ],
        }

        sanitized = sanitize_payload(payload)

        self.assertEqual(sanitized["app_secret"], REDACTED)
        self.assertEqual(sanitized["nested"]["token"], REDACTED)
        self.assertEqual(sanitized["nested"]["safe"], "ok")
        self.assertEqual(sanitized["items"][0]["sign"], REDACTED)

    def test_log_info_requires_trace_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "trace_id"):
            log_info("event", {"safe": "ok"})

    def test_log_info_outputs_json_with_redacted_payload(self) -> None:
        handler = attach_test_handler()
        try:
            log_info(
                "event_info",
                {
                    "trace_id": "TRACE-001",
                    "token": "token-value",
                    "safe": "ok",
                },
            )
        finally:
            detach_test_handler(handler)

        message = json.loads(handler.messages[0])
        self.assertEqual(message["event"], "event_info")
        self.assertEqual(message["payload"]["trace_id"], "TRACE-001")
        self.assertEqual(message["payload"]["token"], REDACTED)
        self.assertEqual(message["payload"]["safe"], "ok")

    def test_log_error_outputs_error_record(self) -> None:
        handler = attach_test_handler()
        try:
            log_error(
                "event_error",
                {
                    "trace_id": "TRACE-001",
                    "APP_SECRET": "secret-value",
                },
            )
        finally:
            detach_test_handler(handler)

        record = handler.records[0]
        message = json.loads(record.getMessage())
        self.assertEqual(record.levelno, logging.ERROR)
        self.assertEqual(message["event"], "event_error")
        self.assertEqual(message["payload"]["APP_SECRET"], REDACTED)

    def test_project_logger_has_console_handler(self) -> None:
        logger = _get_project_logger()

        self.assertTrue(any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers))


class RecordingLogHandler(ListLogHandler):
    """Collects records and messages for logging tests."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        super().emit(record)


def attach_test_handler() -> RecordingLogHandler:
    """Attaches a test handler to the project logger."""

    logger = logging.getLogger("ai_ddts")
    logger.setLevel(logging.INFO)
    handler = RecordingLogHandler()
    logger.addHandler(handler)
    return handler


def detach_test_handler(handler: RecordingLogHandler) -> None:
    """Detaches a test handler from the project logger."""

    logger = logging.getLogger("ai_ddts")
    logger.removeHandler(handler)
