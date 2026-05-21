from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OrderAddressInfo:
    """Receiver address info loaded from xlsx for fallback."""

    receiver_name: str
    phone: str
    address: str


def load_order_address_lookup(xlsx_path: Path | str) -> dict[str, OrderAddressInfo]:
    """Reads xlsx and returns {order_no: OrderAddressInfo} lookup.

    Column mapping (0-indexed):
      Col 2  (index 1) — 订单编号 (key)
      Col 18 (index 17) — 收货人  → receiver_name
      Col 19 (index 18) — 手机    → phone
      Col 20 (index 19) — 收货地址 → address

    Uses a JSON cache file alongside the xlsx to avoid re-reading
    the xlsx on every run. The cache is invalidated when the xlsx
    modification time is newer than the cache.
    """
    path = Path(xlsx_path)
    if not path.exists():
        return {}

    cache_path = path.with_suffix(path.suffix + ".cache.json")
    if _cache_is_fresh(path, cache_path):
        return _load_cache(cache_path)

    lookup = _read_xlsx(path)
    _save_cache(cache_path, lookup)
    return lookup


def _read_xlsx(path: Path) -> dict[str, OrderAddressInfo]:
    import warnings

    import openpyxl

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
        wb = openpyxl.load_workbook(str(path))
    ws = wb.active
    if ws is None:
        wb.close()
        return {}

    lookup: dict[str, OrderAddressInfo] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        order_no = _safe_cell(row, 1)
        if not order_no:
            continue

        lookup[order_no] = OrderAddressInfo(
            receiver_name=_safe_cell(row, 17),
            phone=_safe_cell(row, 18),
            address=_safe_cell(row, 19),
        )

    wb.close()
    return lookup


def _cache_is_fresh(xlsx_path: Path, cache_path: Path) -> bool:
    if not cache_path.exists():
        return False
    return cache_path.stat().st_mtime >= xlsx_path.stat().st_mtime


def _load_cache(cache_path: Path) -> dict[str, OrderAddressInfo]:
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    return {
        key: OrderAddressInfo(**value) for key, value in data.items()
    }


def _save_cache(cache_path: Path, lookup: dict[str, OrderAddressInfo]) -> None:
    data = {
        key: {
            "receiver_name": info.receiver_name,
            "phone": info.phone,
            "address": info.address,
        }
        for key, info in lookup.items()
    }
    cache_path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _safe_cell(row: tuple, index: int) -> str:
    if index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    return str(value).strip()
