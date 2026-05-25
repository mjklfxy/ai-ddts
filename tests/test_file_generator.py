from datetime import datetime
from pathlib import Path
from unittest import TestCase

import openpyxl

from application.file_generator import ORDER_FILE_HEADERS, ExcelFileGenerator, GeneratedFile
from application.order_splitter import GroupOrderBatch
from tests.test_order_splitter import make_order_line


class ExcelFileGeneratorTests(TestCase):
    """Tests Excel generation for group order batches."""

    def test_generates_xlsx_with_prd_headers_and_rows(self) -> None:
        output_dir = workspace_output_dir("default")
        generator = ExcelFileGenerator(
            output_dir=output_dir,
            clock=lambda: datetime(2026, 4, 30, 11, 0, 0),
        )
        line = make_order_line(order_no="SO-001", sku_code="SKU-001")
        line = GroupOrderBatch(group_name="GROUP-A", owner_mobile="", user_id="", order_lines=(line,))

        generated_file = generator.generate(line)

        self.assertIsInstance(generated_file, GeneratedFile)
        self.assertEqual(generated_file.group_name, "GROUP-A")
        self.assertEqual(generated_file.row_count, 1)
        self.assertTrue(generated_file.file_path.name.endswith("GROUP-A_20260430110000.xlsx"))

        rows = read_xlsx(generated_file.file_path)
        self.assertEqual(rows[0], list(ORDER_FILE_HEADERS))
        self.assertEqual(rows[1][0], "SO-001")
        self.assertEqual(rows[1][2], "Goods SKU-001")
        self.assertEqual(rows[1][3], 1)
        self.assertEqual(rows[1][4], "Receiver")

    def test_empty_batch_generates_header_only_file(self) -> None:
        output_dir = workspace_output_dir("empty")
        generator = ExcelFileGenerator(
            output_dir=output_dir,
            clock=lambda: datetime(2026, 4, 30, 11, 0, 0),
        )

        generated_file = generator.generate(
            GroupOrderBatch(group_name="GROUP-A", owner_mobile="", user_id="", order_lines=())
        )

        rows = read_xlsx(generated_file.file_path)
        self.assertEqual(generated_file.row_count, 0)
        self.assertEqual(rows, [list(ORDER_FILE_HEADERS)])

    def test_group_name_is_sanitized_for_file_name(self) -> None:
        output_dir = workspace_output_dir("safe-name")
        generator = ExcelFileGenerator(
            output_dir=output_dir,
            clock=lambda: datetime(2026, 4, 30, 11, 0, 0),
        )

        generated_file = generator.generate(
            GroupOrderBatch(
                group_name="企微 群/001",
                owner_mobile="",
                user_id="",
                order_lines=(make_order_line(order_no="SO-001", sku_code="SKU-001"),),
            )
        )

        self.assertEqual(generated_file.file_path.name, "企微 群_001_20260430110000.xlsx")


def workspace_output_dir(name: str) -> Path:
    """Creates a deterministic workspace-local output directory for tests."""

    output_dir = Path("tmp") / "test_file_generator" / name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def read_xlsx(file_path: Path) -> list[list[object]]:
    """Reads a generated Excel workbook."""

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active
    rows = [list(row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return rows
