from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.supplier import SupplierInfo


class SupplierMappingStore:
    """Persists SKU to supplier mappings synced from ERP."""

    def __init__(
        self,
        mapping_path: str | Path = Path("outputs") / "sku_supplier_mappings.json",
    ) -> None:
        self.mapping_path = Path(mapping_path)

    def load_items(self) -> tuple[SupplierInfo, ...]:
        """Loads supplier mappings from local JSON storage."""

        if not self.mapping_path.exists():
            return ()

        data = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        items = _items_from_payload(data)
        return tuple(_supplier_from_dict(item) for item in items)

    def load_map(self) -> dict[str, SupplierInfo]:
        """Loads supplier mappings keyed by SKU code."""

        return {item.sku_code: item for item in self.load_items()}

    def replace_from_payload(self, payload: dict[str, Any]) -> tuple[SupplierInfo, ...]:
        """Replaces mappings using an API-safe payload."""

        items = tuple(_supplier_from_dict(item) for item in _items_from_payload(payload))
        self.replace(items)
        return items

    def replace(self, items: tuple[SupplierInfo, ...] | list[SupplierInfo]) -> None:
        """Replaces all local supplier mappings."""

        normalized_items = tuple(_deduplicate(items))
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
        self.mapping_path.write_text(
            json.dumps(
                {
                    "items": [supplier_to_dict(item) for item in normalized_items],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def supplier_to_dict(supplier: SupplierInfo) -> dict[str, str]:
    """Converts SupplierInfo into JSON-compatible data."""

    return {
        "sku_code": supplier.sku_code,
        # === MODIFIED START ===
        # 原因：供应商对照不再维护供应商编码，接口与本地文件只输出供应商名称。
        # 影响范围：供应商映射 API 与持久化文件。
        # === MODIFIED END ===
        "supplier_name": supplier.supplier_name,
    }


def suppliers_to_payload(items: tuple[SupplierInfo, ...] | list[SupplierInfo]) -> dict[str, object]:
    """Converts supplier mappings into an API response payload."""

    return {
        "items": [supplier_to_dict(item) for item in items],
    }


def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("supplier mapping payload must be an object")

    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("supplier mapping items must be a list")

    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("supplier mapping items must be objects")
        result.append(item)
    return result


def _supplier_from_dict(data: dict[str, Any]) -> SupplierInfo:
    return SupplierInfo(
        sku_code=_required_string(data, "sku_code"),
        # === MODIFIED START ===
        # 原因：历史数据可能仍包含 supplier_code，但新口径不再要求或使用该字段。
        # 影响范围：供应商映射读取与保存兼容。
        # === MODIFIED END ===
        supplier_name=_required_string(data, "supplier_name"),
    )


def _deduplicate(items: tuple[SupplierInfo, ...] | list[SupplierInfo]) -> tuple[SupplierInfo, ...]:
    seen_skus: set[str] = set()
    result: list[SupplierInfo] = []
    for item in items:
        if item.sku_code in seen_skus:
            raise ValueError(f"Duplicate supplier mapping sku_code: {item.sku_code}")
        seen_skus.add(item.sku_code)
        result.append(item)
    return tuple(result)


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
