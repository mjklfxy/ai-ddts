from __future__ import annotations

import csv
import json
import urllib.request
from collections.abc import Callable
from datetime import datetime
from io import StringIO
from pathlib import Path

from shared.logging.logger import log_info, log_error

DEFAULT_URL = (
    "https://state.renruikeji.cn/api/mall/manage/mallgoodsV2/exportCloudWarehouseSku"
)
DEFAULT_LOCAL_PATH = Path("outputs") / "sku_supplier_mappings.json"

Clock = Callable[[], datetime]


class CloudWarehouseClient:
    """Local-persisted SKU-to-supplier lookup synced from the cloud warehouse export API."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        local_path: str | Path = DEFAULT_LOCAL_PATH,
        clock: Clock | None = None,
        urlopen: Callable[..., object] | None = None,
    ) -> None:
        if not url.strip():
            raise ValueError("url must be a non-empty string")
        self.url = url.strip()
        self.local_path = Path(local_path)
        self.clock = clock or datetime.now
        self._urlopen = urlopen
        self._mapping: dict[str, str] = {}
        self._loaded = False

    def get_supplier(self, sku_name: str) -> str | None:
        """Returns the supplier for a given SKU name, or None if not found."""
        if not sku_name or not sku_name.strip():
            return None

        key = sku_name.strip()
        self._ensure_loaded()

        if key in self._mapping:
            return self._mapping[key] or None

        self._sync()
        return self._mapping.get(key)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            self._read_local()
        except Exception:
            pass

    def _read_local(self) -> None:
        if not self.local_path.exists():
            return
        data = json.loads(self.local_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        items = data.get("items")
        if isinstance(items, list):
            mapping: dict[str, str] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                sku_code = item.get("sku_code")
                supplier_name = item.get("supplier_name")
                if isinstance(sku_code, str) and sku_code.strip():
                    name = sku_code.strip()
                    if isinstance(supplier_name, str) and supplier_name.strip():
                        mapping[name] = supplier_name.strip()
                    else:
                        mapping[name] = ""
            self._mapping = mapping

    def _sync(self) -> None:
        try:
            raw_csv = self._fetch_csv()
            self._mapping = self._parse_csv(raw_csv)
            self._write_local()
            log_info(
                "cloud_warehouse_synced",
                {
                    "trace_id": "cloud-warehouse",
                    "sku_count": len(self._mapping),
                    "url": self.url,
                },
            )
        except Exception as exc:
            log_error(
                "cloud_warehouse_sync_failed",
                {
                    "trace_id": "cloud-warehouse",
                    "url": self.url,
                    "error_type": exc.__class__.__name__,
                    "reason": str(exc)[:200],
                },
            )

    def _write_local(self) -> None:
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        items = [
            {"sku_code": name, "supplier_name": supplier}
            for name, supplier in sorted(
                self._mapping.items(), key=lambda item: item[0]
            )
            if supplier
        ]
        self.local_path.write_text(
            json.dumps(
                {"items": items},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _fetch_csv(self) -> str:
        urlopen = self._urlopen or urllib.request.urlopen
        request = urllib.request.Request(self.url, method="GET")
        try:
            response = urlopen(request, timeout=30)
            try:
                raw_body = response.read()
                content_type = response.headers.get("Content-Type", "")
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except Exception as exc:
            raise ValueError(
                f"Cloud warehouse API request failed: {exc.__class__.__name__}"
            ) from exc
        if "csv" not in content_type and "text" not in content_type:
            raise ValueError(
                f"Cloud warehouse API returned unexpected Content-Type: {content_type}"
            )

        return raw_body.decode("utf-8")

    @staticmethod
    def _repair_broken_rows(raw_csv: str) -> str:
        """Rejoin rows that were split by unquoted newlines inside field values."""
        lines = raw_csv.splitlines()
        if not lines:
            return raw_csv

        header = lines[0]
        repaired: list[str] = [header]

        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            # A row that starts with a digit sequence is a new SKU entry.
            # Rows that don't are continuation of a broken field from the previous row.
            if stripped[0].isdigit() and "," in stripped:
                repaired.append(stripped)
            elif repaired:
                repaired[-1] += stripped
            else:
                repaired.append(stripped)

        return "\n".join(repaired)

    @staticmethod
    def _parse_csv(raw_csv: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        repaired_csv = CloudWarehouseClient._repair_broken_rows(raw_csv)
        reader = csv.reader(StringIO(repaired_csv))
        header = next(reader, None)
        if header is None:
            return mapping

        try:
            name_index = header.index("名称")
            supplier_index = header.index("供应商")
        except ValueError as exc:
            raise ValueError(
                f"Cloud warehouse CSV missing expected columns: {exc}"
            ) from exc

        for row in reader:
            if len(row) <= max(name_index, supplier_index):
                continue
            name = row[name_index].strip()
            supplier = row[supplier_index].strip()
            if name:
                mapping[name] = supplier

        return mapping
