from __future__ import annotations

from pathlib import Path
from typing import Any


def load_restricted_regions_from_xlsx(xlsx_path: str | Path) -> list[dict[str, str | None]]:
    """Read restricted region data from an .xls or .xlsx file.

    Column mapping (0-indexed):
      Col 0 — 产品名称（可能合并多行，一个单元格内多个产品用换行分隔）
      Col 1 — 省（可能合并多行）
      Col 2 — 市（可能合并多行）

    Supports .xls (via xlrd) and .xlsx (via openpyxl).
    """
    path = Path(xlsx_path)
    suffix = path.suffix.lower()

    if suffix == ".xls":
        return _load_via_xlrd(path)
    if suffix in (".xlsx", ".xlsm"):
        return _load_via_openpyxl(path)
    raise ValueError(f"不支持的文件格式: {suffix}")


def _load_via_xlrd(path: Path) -> list[dict[str, str | None]]:
    import xlrd

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    raw_rows: list[tuple[str, str, str]] = []
    last_sku = ""
    last_province = ""
    last_city = ""

    for row_idx in range(1, ws.nrows):
        sku_original = _cell_str_xls(ws, row_idx, 0)
        province_original = _cell_str_xls(ws, row_idx, 1)
        city_original = _cell_str_xls(ws, row_idx, 2)

        if not sku_original and not province_original and not city_original:
            continue

        sku_text = sku_original or last_sku
        province = province_original or last_province
        city = city_original or last_city

        last_sku = sku_text
        last_province = province
        last_city = city
        raw_rows.append((sku_text, province, city))

    return _expand_products(raw_rows)


def _load_via_openpyxl(path: Path) -> list[dict[str, str | None]]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path))
    ws = wb.active

    raw_rows: list[tuple[str, str, str]] = []
    last_sku = ""
    last_province = ""
    last_city = ""

    for row in ws.iter_rows(min_row=2, values_only=True):
        sku_original = _cell_str(row, 0)
        province_original = _cell_str(row, 1)
        city_original = _cell_str(row, 2)

        if not sku_original and not province_original and not city_original:
            continue

        sku_text = sku_original or last_sku
        province = province_original or last_province
        city = city_original or last_city

        last_sku = sku_text
        last_province = province
        last_city = city
        raw_rows.append((sku_text, province, city))

    wb.close()
    return _expand_products(raw_rows)


def _cell_str(row: tuple[Any, ...], index: int) -> str:
    if index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    return str(value).strip()


def _cell_str_xls(ws, row_idx: int, col_idx: int) -> str:
    try:
        value = ws.cell_value(row_idx, col_idx)
    except IndexError:
        return ""
    if value is None:
        return ""
    return str(value).strip()


def _expand_products(raw_rows: list[tuple[str, str, str]]) -> list[dict[str, str | None]]:
    result: list[dict[str, str | None]] = []
    for sku_text, province, city in raw_rows:
        for product in _split_products(sku_text):
            result.append({
                "sku_code": product,
                "province": province or None,
                "city": city or None,
            })
    return result


def _split_products(text: str) -> list[str]:
    """Split products by newline within a cell."""
    return [part.strip() for part in text.split("\n") if part.strip()]


# =====================================================================
# Demo
# =====================================================================
if __name__ == "__main__":
    import sys
    import io

    # 修复 Windows CMD 中文乱码
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("Usage: python demo/demo_xlsx_parser.py <file_path>")
        print("  Example: python demo/demo_xlsx_parser.py ./demo/test.xlsx")
        sys.exit(1)

    regions = load_restricted_regions_from_xlsx(sys.argv[1])

    print(f"共解析出 {len(regions)} 条限发记录:\n")
    for item in regions:
        city_display = item["city"] or "不限"
        print(f"  {item['sku_code']}  →  {item['province']} / {city_display}")
