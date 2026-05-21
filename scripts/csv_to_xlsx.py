"""Convert a CSV file to XLSX, repairing rows broken by unquoted newlines in field values.

Usage:
    python scripts/csv_to_xlsx.py outputs/order_files/123456_20260513145823.csv
    python scripts/csv_to_xlsx.py input.csv output.xlsx
"""

from __future__ import annotations

import csv
import sys
from io import StringIO
from pathlib import Path

from openpyxl import Workbook


def _repair_broken_rows(raw_csv: str) -> str:
    """Rejoin rows that were split by unquoted newlines inside field values.

    A row that starts with a valid first-column value begins a new record;
    continuation lines are appended to the previous row.
    """
    lines = raw_csv.splitlines()
    if not lines:
        return raw_csv

    header = lines[0]
    repaired: list[str] = [header]

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        # A new record starts when the first char matches the expected first-column
        # pattern (e.g. "JY2026..." or similar). Otherwise it's a continuation line.
        if _looks_like_first_column(stripped):
            repaired.append(stripped)
        elif repaired:
            repaired[-1] += " " + stripped
        else:
            repaired.append(stripped)

    return "\n".join(repaired)


def _looks_like_first_column(text: str) -> bool:
    """Heuristic: the first column of this CSV starts with uppercase letters followed by digits (e.g. JY202605138079)."""
    first_field = text.split(",", 1)[0].strip().strip('"')
    if not first_field:
        return False
    has_alpha = any(c.isalpha() for c in first_field)
    has_digit = any(c.isdigit() for c in first_field)
    return has_alpha and has_digit and len(first_field) >= 6


def csv_to_xlsx(csv_path: str | Path, xlsx_path: str | Path | None = None) -> Path:
    """Convert a CSV file to XLSX, handling broken rows caused by embedded newlines."""
    csv_path = Path(csv_path)
    if xlsx_path is None:
        xlsx_path = csv_path.with_suffix(".xlsx")
    else:
        xlsx_path = Path(xlsx_path)

    raw_text = csv_path.read_text(encoding="utf-8")
    repaired = _repair_broken_rows(raw_text)

    reader = csv.reader(StringIO(repaired))
    rows = list(reader)

    if not rows:
        print("CSV is empty, nothing to convert.")
        return Path(xlsx_path)

    wb = Workbook()
    ws = wb.active
    ws.title = csv_path.stem[:31]

    for row in rows:
        cleaned = [_clean_cell(cell) for cell in row]
        ws.append(cleaned)

    # Auto-adjust column widths
    for col_cells in ws.columns:
        col_letter = col_cells[0].column_letter
        max_width = max(
            (len(str(cell.value or "")) for cell in col_cells if cell.value),
            default=8,
        )
        ws.column_dimensions[col_letter].width = min(max_width + 2, 60)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)
    print(f"Converted {csv_path} → {xlsx_path} ({len(rows)} rows)")
    return Path(xlsx_path)


def _clean_cell(value: str) -> str:
    """Normalize cell content: strip stray carriage returns and condense whitespace."""
    if not value:
        return ""
    # Remove stray \r and replace tabs with spaces
    cleaned = value.replace("\r", "").replace("\t", " ")
    # Collapse multiple spaces but keep intentional newlines from the CSV repair
    return cleaned.strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <input.csv> [output.xlsx]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    csv_to_xlsx(input_path, output_path)


# cd "d:/Study/wuliu/AI-DDTS" && python scripts/csv_to_xlsx.py "outputs/order_files/xxx.csv"
