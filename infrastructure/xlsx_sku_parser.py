from __future__ import annotations

from pathlib import Path
from typing import Any


def load_skus_from_xlsx(xlsx_path: str | Path) -> list[str]:
    """Read SKU list from column A of an .xls or .xlsx file.

    Column mapping (0-indexed):
      Col 0 — SKU 名称（可能合并多行，一个单元格内多个 SKU 用换行分隔）

    Returns deduplicated list preserving order.
    """
    path = Path(xlsx_path)
    suffix = path.suffix.lower()

    if suffix == ".xls":
        return _load_via_xlrd(path)
    if suffix in (".xlsx", ".xlsm"):
        return _load_via_openpyxl(path)
    raise ValueError(f"不支持的文件格式: {suffix}")


def _load_via_xlrd(path: Path) -> list[str]:
    import xlrd

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    raw: list[str] = []
    last_sku = ""

    for row_idx in range(1, ws.nrows):
        sku_original = _cell_str_xls(ws, row_idx, 0)
        if not sku_original:
            sku_text = last_sku
        else:
            sku_text = sku_original
            last_sku = sku_text
        if sku_text:
            raw.append(sku_text)

    return _expand_and_dedup(raw)


def _load_via_openpyxl(path: Path) -> list[str]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path))
    ws = wb.active

    raw: list[str] = []
    last_sku = ""

    for row in ws.iter_rows(min_row=2, values_only=True):
        sku_original = _cell_str(row, 0)
        if not sku_original:
            sku_text = last_sku
        else:
            sku_text = sku_original
            last_sku = sku_text
        if sku_text:
            raw.append(sku_text)

    wb.close()
    return _expand_and_dedup(raw)


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


def _expand_and_dedup(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for text in raw:
        for part in _split_products(text):
            if part not in seen:
                seen.add(part)
                result.append(part)
    return result


def _split_products(text: str) -> list[str]:
    """Split products by newline within a cell."""
    return [part.strip() for part in text.split("\n") if part.strip()]


def load_skus_from_bytes(data: bytes, filename: str = "upload.xlsx") -> list[str]:
    """Parse SKU list from in-memory xlsx/xls bytes."""
    import tempfile

    suffix = Path(filename).suffix.lower()
    if suffix not in (".xls", ".xlsx", ".xlsm"):
        raise ValueError(f"不支持的文件格式: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        return load_skus_from_xlsx(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
