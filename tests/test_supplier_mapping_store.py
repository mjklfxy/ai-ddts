import json
from pathlib import Path
from unittest import TestCase

from application.supplier_mapping_store import SupplierMappingStore
from domain.supplier import SupplierInfo


class SupplierMappingStoreTests(TestCase):
    """Tests persistence for ERP SKU to supplier mappings."""

    def test_missing_mapping_file_returns_empty_items(self) -> None:
        store = SupplierMappingStore(
            mapping_path=Path("tmp") / "test_supplier_mapping_store" / "missing.json"
        )

        self.assertEqual(store.load_items(), ())
        self.assertEqual(store.load_map(), {})

    def test_replace_from_payload_persists_supplier_mappings(self) -> None:
        mapping_path = Path("tmp") / "test_supplier_mapping_store" / "mappings.json"
        if mapping_path.exists():
            mapping_path.unlink()
        store = SupplierMappingStore(mapping_path=mapping_path)

        items = store.replace_from_payload(
            {
                "items": [
                    {
                        "sku_code": " SKU-001 ",
                        "supplier_name": " Supplier A ",
                    }
                ]
            }
        )

        self.assertEqual(items, (make_supplier(),))
        self.assertEqual(SupplierMappingStore(mapping_path=mapping_path).load_items(), (make_supplier(),))
        persisted = json.loads(mapping_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["items"][0]["sku_code"], "SKU-001")

    def test_duplicate_sku_is_rejected(self) -> None:
        store = SupplierMappingStore(
            mapping_path=Path("tmp") / "test_supplier_mapping_store" / "duplicate.json"
        )

        with self.assertRaisesRegex(ValueError, "Duplicate supplier mapping sku_code"):
            store.replace(
                [
                    make_supplier(),
                    make_supplier(),
                ]
            )

    def test_invalid_payload_is_rejected(self) -> None:
        store = SupplierMappingStore(
            mapping_path=Path("tmp") / "test_supplier_mapping_store" / "invalid.json"
        )

        with self.assertRaisesRegex(ValueError, "items must be a list"):
            store.replace_from_payload({"items": {}})


def make_supplier() -> SupplierInfo:
    """Builds one supplier mapping for store tests."""

    return SupplierInfo(
        sku_code="SKU-001",
        supplier_name="Supplier A",
    )
