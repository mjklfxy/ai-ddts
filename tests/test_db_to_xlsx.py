from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from infrastructure.db_to_xlsx import describe_export_file


class DbToXlsxTests(TestCase):
    """Tests export-file state reporting for the desktop RPA exporter."""

    def test_describe_export_file_reports_missing_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "missing.xlsx"

            event, payload = describe_export_file(target_path)

        self.assertEqual(event, "export_file_missing")
        self.assertEqual(payload["path"], str(target_path))
        self.assertEqual(payload["exists"], False)

    def test_describe_export_file_reports_detected_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "orders.xlsx"
            target_path.write_bytes(b"demo-xlsx")

            event, payload = describe_export_file(target_path)

        self.assertEqual(event, "export_file_detected")
        self.assertEqual(payload["path"], str(target_path))
        self.assertEqual(payload["exists"], True)
        self.assertEqual(payload["size_bytes"], 9)
        self.assertIn("modified_at", payload)
