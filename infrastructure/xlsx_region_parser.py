from __future__ import annotations

from pathlib import Path
from typing import Any
import re

_CITY_REMARKS = {"新增", "新加", "备注", "新增区域", "新增限发"}


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

    # === MODIFIED START ===
    # 原因：限发区域 Excel 的产品、省、市三列都可能存在合并单元格；逐行 forward-fill 会重复展开，
    #       且会把“新增”等备注误当作市区。
    # 影响范围：限发区域 XLSX 上传解析。
    try:
        merged_lookup = _merged_lookup(ws)
        raw_rows: list[tuple[str, str, str]] = []
        seen_product_blocks: set[tuple[int, int]] = set()

        for row_idx in range(2, ws.max_row + 1):
            product_anchor = _merged_anchor(merged_lookup, row_idx, 1)
            if product_anchor in seen_product_blocks:
                continue
            seen_product_blocks.add(product_anchor)

            sku_text = _cell_value(ws, merged_lookup, row_idx, 1)
            if not sku_text:
                continue

            start_row, end_row = _row_span(merged_lookup, row_idx, 1)
            for region_row_idx in range(start_row, end_row + 1):
                province = _cell_value(ws, merged_lookup, region_row_idx, 2)
                city = _normalized_city(
                    _cell_value(ws, merged_lookup, region_row_idx, 3)
                )
                if not province:
                    continue
                raw_rows.append((sku_text, province, city))

        return _dedupe_regions(_expand_products(raw_rows))
    finally:
        wb.close()
    # === MODIFIED END ===


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
    # === MODIFIED START ===
    # 原因：同一个产品块需要先拆 SKU，再套用块内全部限发区域，避免输出顺序和合并行数耦合。
    # 影响范围：限发区域 XLS/XLSX 上传解析。
    result: list[dict[str, str | None]] = []
    grouped_rows: list[tuple[str, list[tuple[str, str]]]] = []
    for sku_text, province, city in raw_rows:
        if grouped_rows and grouped_rows[-1][0] == sku_text:
            grouped_rows[-1][1].append((province, city))
        else:
            grouped_rows.append((sku_text, [(province, city)]))

    for sku_text, regions in grouped_rows:
        for product in _split_products(sku_text):
            for province, city in regions:
                result.append({
                    "sku_code": product,
                    "province": province or None,
                    "city": city or None,
                })
    return result
    # === MODIFIED END ===


def _split_products(text: str) -> list[str]:
    """Split products by newline within a cell."""
    # === MODIFIED START ===
    # 原因：Excel 粘贴数据可能用超长空白分隔 SKU；普通空格可能是 SKU 名称的一部分，不能拆。
    # 影响范围：限发区域 XLS/XLSX 上传解析。
    normalized = text.replace("\u00a0", " ").replace("\u3000", " ")
    return [
        part.strip()
        for part in re.split(r"(?:\r\n|\r|\n|\t| {8,})+", normalized)
        if part.strip()
    ]
    # === MODIFIED END ===


# === MODIFIED START ===
# 原因：集中处理 XLSX 合并单元格、备注市区和重复限发区域，避免上传解析生成错误配置。
# 影响范围：限发区域 XLSX 上传解析。
def _merged_lookup(ws) -> dict[tuple[int, int], tuple[int, int, int, int]]:
    lookup: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for cell_range in ws.merged_cells.ranges:
        bounds = (
            cell_range.min_row,
            cell_range.min_col,
            cell_range.max_row,
            cell_range.max_col,
        )
        for row_idx in range(cell_range.min_row, cell_range.max_row + 1):
            for col_idx in range(cell_range.min_col, cell_range.max_col + 1):
                lookup[(row_idx, col_idx)] = bounds
    return lookup


def _merged_anchor(
    merged_lookup: dict[tuple[int, int], tuple[int, int, int, int]],
    row_idx: int,
    col_idx: int,
) -> tuple[int, int]:
    bounds = merged_lookup.get((row_idx, col_idx))
    if bounds is None:
        return (row_idx, col_idx)
    return (bounds[0], bounds[1])


def _row_span(
    merged_lookup: dict[tuple[int, int], tuple[int, int, int, int]],
    row_idx: int,
    col_idx: int,
) -> tuple[int, int]:
    bounds = merged_lookup.get((row_idx, col_idx))
    if bounds is None:
        return (row_idx, row_idx)
    return (bounds[0], bounds[2])


def _cell_value(
    ws,
    merged_lookup: dict[tuple[int, int], tuple[int, int, int, int]],
    row_idx: int,
    col_idx: int,
) -> str:
    anchor_row, anchor_col = _merged_anchor(merged_lookup, row_idx, col_idx)
    value = ws.cell(anchor_row, anchor_col).value
    if value is None:
        return ""
    return str(value).strip()


def _normalized_city(city: str) -> str:
    if city in _CITY_REMARKS:
        return ""
    return city


def _dedupe_regions(items: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    result: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            item["sku_code"] or "",
            item["province"] or "",
            item["city"] or "",
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
# === MODIFIED END ===


def load_restricted_regions_from_bytes(data: bytes, filename: str = "upload.xlsx") -> list[dict[str, str | None]]:
    """Parse restricted regions from in-memory xlsx/xls bytes.

    Useful for file upload scenarios where writing to disk is undesirable.
    """
    import tempfile

    suffix = Path(filename).suffix.lower()
    if suffix not in (".xls", ".xlsx", ".xlsm"):
        raise ValueError(f"不支持的文件格式: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        return load_restricted_regions_from_xlsx(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
