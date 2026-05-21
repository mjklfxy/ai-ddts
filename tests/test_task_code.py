from datetime import datetime
from unittest import TestCase

from application.task_code import DailyTaskCodeGenerator, max_existing_sequence


class DailyTaskCodeGeneratorTests(TestCase):
    """Tests task batch code generation rules."""

    def test_generates_next_sequence_from_existing_codes(self) -> None:
        generator = DailyTaskCodeGenerator(
            existing_codes_provider=lambda: (
                "202604300001",
                "202604300009",
                "202604290099",
                "TRACE-OLD",
            ),
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertEqual(generator(), "202604300010")
        self.assertEqual(generator(), "202604300011")

    def test_sequence_resets_by_date_prefix(self) -> None:
        generator = DailyTaskCodeGenerator(
            existing_codes_provider=lambda: ("202604300099",),
            clock=lambda: datetime(2026, 5, 1, 9, 0, 0),
        )

        self.assertEqual(generator(), "202605010001")

    def test_rejects_invalid_date_prefix(self) -> None:
        with self.assertRaisesRegex(ValueError, "date_prefix"):
            max_existing_sequence(existing_codes=(), date_prefix="2026-04-30")
