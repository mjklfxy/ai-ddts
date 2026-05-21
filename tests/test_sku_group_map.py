from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from application.sku_group_map import SkuGroupMapStore
from domain.sku_group_info import SkuGroupInfo


class SkuGroupMapStoreTests(TestCase):
    """Tests persistence of SKU push-group configuration."""

    def test_load_preserves_user_id_from_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = write_config(Path(temp_dir) / "config.json")

            mapping = SkuGroupMapStore(config_path).load()

        self.assertEqual(
            mapping["SKU-001"],
            SkuGroupInfo(
                group_name="GROUP-A",
                owner_mobile="15176152071",
                user_id="USER-001",
            ),
        )

    def test_save_preserves_user_id_to_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = write_config(Path(temp_dir) / "config.json")
            store = SkuGroupMapStore(config_path)

            store.set(
                "SKU-002",
                "GROUP-B",
                owner_mobile="15176152072",
                user_id="USER-002",
            )

            persisted = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(
            persisted["rules"]["sku_group_map"]["SKU-002"],
            {
                "group_name": "GROUP-B",
                "owner_mobile": "15176152072",
                "user_id": "USER-002",
            },
        )


def write_config(config_path: Path) -> Path:
    """Writes a minimal config containing one SKU group mapping."""

    config_path.write_text(
        json.dumps(
            {
                "rules": {
                    "sku_group_map": {
                        "SKU-001": {
                            "group_name": "GROUP-A",
                            "owner_mobile": "15176152071",
                            "user_id": "USER-001",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path
