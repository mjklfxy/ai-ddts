from __future__ import annotations

from pathlib import Path
from typing import Any


def load_sku_groups_from_xlsx(xlsx_path: str | Path) -> list[dict[str, str]]:
    """Read SKU group data from an .xls or .xlsx file.

    Column mapping (0-indexed):
      Col 0 — SKU 名称（可能合并多行，一个单元格内多个 SKU 用换行分隔）
      Col 1 — 群名称（可能合并多行）
      Col 2 — 群主手机号（可能合并多行）

    Supports .xls (via xlrd) and .xlsx (via openpyxl).
    """
    path = Path(xlsx_path)
    suffix = path.suffix.lower()

    if suffix == ".xls":
        return _load_via_xlrd(path)
    if suffix in (".xlsx", ".xlsm"):
        return _load_via_openpyxl(path)
    raise ValueError(f"不支持的文件格式: {suffix}")


def _load_via_xlrd(path: Path) -> list[dict[str, str]]:
    import xlrd

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    raw_rows: list[tuple[str, str, str]] = []
    last_sku = ""
    last_group = ""
    last_mobile = ""

    for row_idx in range(1, ws.nrows):
        sku_original = _cell_str_xls(ws, row_idx, 0)
        group_original = _cell_str_xls(ws, row_idx, 1)
        mobile_original = _cell_str_xls(ws, row_idx, 2)

        if not sku_original and not group_original and not mobile_original:
            continue

        sku_text = sku_original or last_sku
        group = group_original or last_group
        mobile = mobile_original or last_mobile

        last_sku = sku_text
        last_group = group
        last_mobile = mobile
        raw_rows.append((sku_text, group, mobile))

    return _expand_skus(raw_rows)


def _load_via_openpyxl(path: Path) -> list[dict[str, str]]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path))
    ws = wb.active

    raw_rows: list[tuple[str, str, str]] = []
    last_sku = ""
    last_group = ""
    last_mobile = ""

    for row in ws.iter_rows(min_row=2, values_only=True):
        sku_original = _cell_str(row, 0)
        group_original = _cell_str(row, 1)
        mobile_original = _cell_str(row, 2)

        if not sku_original and not group_original and not mobile_original:
            continue

        sku_text = sku_original or last_sku
        group = group_original or last_group
        mobile = mobile_original or last_mobile

        last_sku = sku_text
        last_group = group
        last_mobile = mobile
        raw_rows.append((sku_text, group, mobile))

    wb.close()
    return _expand_skus(raw_rows)


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


def _expand_skus(raw_rows: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for sku_text, group, mobile in raw_rows:
        for product in _split_products(sku_text):
            result.append({
                "sku_code": product,
                "group_name": group,
                "owner_mobile": mobile,
            })
    return result


def _split_products(text: str) -> list[str]:
    """Split products by newline within a cell."""
    return [part.strip() for part in text.split("\n") if part.strip()]


def load_sku_groups_from_bytes(data: bytes, filename: str = "upload.xlsx") -> list[dict[str, str]]:
    """Parse SKU groups from in-memory xlsx/xls bytes."""
    import tempfile

    suffix = Path(filename).suffix.lower()
    if suffix not in (".xls", ".xlsx", ".xlsm"):
        raise ValueError(f"不支持的文件格式: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        return load_sku_groups_from_xlsx(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
