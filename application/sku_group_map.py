from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.sku_group_info import SkuGroupInfo


class SkuGroupMapStore:
    """Reads and writes sku_group_map inside config.json."""

    def __init__(self, config_path: str | Path = Path("config") / "config.json") -> None:
        self.config_path = Path(config_path)

    # -- read ----------------------------------------------------------------

    def load(self) -> dict[str, SkuGroupInfo]:
        """Returns the current sku_group_map from config.json."""
        data = self._read_config()
        rules = data.get("rules", {}) if isinstance(data, dict) else {}
        raw = rules.get("sku_group_map", {}) if isinstance(rules, dict) else {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, SkuGroupInfo] = {}
        for k, v in raw.items():
            key = str(k).strip()
            if not key:
                continue
            if isinstance(v, str) and v.strip():
                result[key] = SkuGroupInfo(group_name=v.strip(), owner_mobile="", user_id="")
            elif isinstance(v, dict):
                group_name = str(v.get("group_name", "")).strip()
                owner_mobile = str(v.get("owner_mobile", "")).strip()
                # === MODIFIED START ===
                # 原因：SKU 群配置新增 user_id 后，独立 Store 读写也必须保留该字段。
                # 影响范围：SkuGroupMapStore 读取结果和后续推送身份解析。
                user_id = str(v.get("user_id", "")).strip()
                # === MODIFIED END ===
                if group_name:
                    result[key] = SkuGroupInfo(
                        group_name=group_name,
                        owner_mobile=owner_mobile,
                        user_id=user_id,
                    )
        return result

    def get(self, sku_code: str) -> SkuGroupInfo | None:
        """Returns the SkuGroupInfo for a single SKU, or None."""
        return self.load().get(sku_code.strip())

    def list_groups(self) -> dict[str, list[str]]:
        """Returns {group_name: [sku_code, ...]} grouped by group."""
        result: dict[str, list[str]] = {}
        for sku, info in self.load().items():
            result.setdefault(info.group_name, []).append(sku)
        return result

    # -- write ---------------------------------------------------------------

    def add(self, sku_code: str, group_name: str, owner_mobile: str = "", user_id: str = "") -> None:
        """Adds a mapping. Raises ValueError if the SKU already exists."""
        sku = sku_code.strip()
        gn = group_name.strip()
        if not sku:
            raise ValueError("sku_code must be a non-empty string")
        if not gn:
            raise ValueError("group_name must be a non-empty string")
        current = self.load()
        if sku in current:
            raise ValueError(f"SKU already mapped: {sku} → {current[sku].group_name}")
        current[sku] = SkuGroupInfo(group_name=gn, owner_mobile=owner_mobile.strip(), user_id=user_id.strip())
        self._save(current)

    def update(self, sku_code: str, group_name: str, owner_mobile: str = "", user_id: str = "") -> None:
        """Updates an existing mapping. Raises ValueError if not found."""
        sku = sku_code.strip()
        gn = group_name.strip()
        if not sku:
            raise ValueError("sku_code must be a non-empty string")
        if not gn:
            raise ValueError("group_name must be a non-empty string")
        current = self.load()
        if sku not in current:
            raise ValueError(f"SKU not found: {sku}")
        current[sku] = SkuGroupInfo(group_name=gn, owner_mobile=owner_mobile.strip(), user_id=user_id.strip())
        self._save(current)

    def set(self, sku_code: str, group_name: str, owner_mobile: str = "", user_id: str = "") -> None:
        """Adds or updates a mapping (upsert)."""
        sku = sku_code.strip()
        gn = group_name.strip()
        if not sku:
            raise ValueError("sku_code must be a non-empty string")
        if not gn:
            raise ValueError("group_name must be a non-empty string")
        current = self.load()
        current[sku] = SkuGroupInfo(group_name=gn, owner_mobile=owner_mobile.strip(), user_id=user_id.strip())
        self._save(current)

    def remove(self, sku_code: str) -> None:
        """Removes a mapping by SKU. Raises ValueError if not found."""
        sku = sku_code.strip()
        current = self.load()
        if sku not in current:
            raise ValueError(f"SKU not found: {sku}")
        del current[sku]
        self._save(current)

    def replace(self, mapping: dict[str, SkuGroupInfo]) -> None:
        """Replaces the entire sku_group_map."""
        validated: dict[str, SkuGroupInfo] = {}
        for k, v in mapping.items():
            key = k.strip()
            if not key:
                raise ValueError("sku_group_map keys must be non-empty strings")
            if not isinstance(v, SkuGroupInfo):
                raise ValueError("sku_group_map values must be SkuGroupInfo")
            if not v.group_name.strip():
                raise ValueError("sku_group_map values must have non-empty group_name")
            if key in validated:
                raise ValueError(f"Duplicate SKU in sku_group_map: {key}")
            validated[key] = v
        self._save(validated)

    def rename_group(self, old_group_name: str, new_group_name: str) -> int:
        """Renames a group_name across all mappings. Returns count of updated SKUs."""
        old = old_group_name.strip()
        new = new_group_name.strip()
        if not old or not new:
            raise ValueError("group_name must be a non-empty string")
        current = self.load()
        count = 0
        for sku, info in list(current.items()):
            if info.group_name == old:
                current[sku] = SkuGroupInfo(
                    group_name=new,
                    owner_mobile=info.owner_mobile,
                    user_id=info.user_id,
                )
                count += 1
        if count:
            self._save(current)
        return count

    # -- internal ------------------------------------------------------------

    def _read_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Config must be a JSON object")
        return data

    def _save(self, mapping: dict[str, SkuGroupInfo]) -> None:
        data = self._read_config()
        data.setdefault("rules", {})["sku_group_map"] = {
            sku: {
                "group_name": info.group_name,
                "owner_mobile": info.owner_mobile,
                # === MODIFIED START ===
                # 原因：完整保存推送身份配置，避免 user_id 丢失导致手机号/群配置表现异常。
                # 影响范围：config.rules.sku_group_map。
                "user_id": info.user_id,
                # === MODIFIED END ===
            }
            for sku, info in mapping.items()
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
