from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import sub
from typing import Any

from application.pipeline import PipelineBatchDelivery
from application.task_service import TaskContext


SPECIAL_PUSH_ORDER_CSV_HEADERS = (
    "trace_id",
    "临时推送ID",
    "推送群",
    "群主手机号",
    "关联单号",
    "发货单号",
    "仓库编码",
    "仓库",
    "SKU（商品名称）",
    "货品摘要",
    "数量",
    "收件人",
    "地址",
    "电话",
    "物流公司",
    "物流单号",
    "推送文件",
    "消息追踪号",
)


@dataclass(frozen=True, slots=True)
class StoredSpecialPushOrder:
    """Persisted temporary push order detail."""

    trace_id: str
    temp_push_id: str
    group_name: str
    owner_mobile: str
    order_no: str
    delivery_order_no: str
    warehouse_code: str
    warehouse_name: str
    sku_code: str
    goods_summary: str
    quantity: int
    receiver_name: str
    address: str
    phone: str
    logistics_company: str
    logistics_no: str
    file_path: str
    message_tracking_id: str


class SpecialPushOrderStore:
    """Persists temporary push order details and exports them as CSV."""

    def __init__(
        self,
        temp_push_id: str,
        base_dir: str | Path = Path("outputs") / "special_push",
    ) -> None:
        self.temp_push_id = temp_push_id
        self.base_dir = Path(base_dir) / temp_push_id
        self.history_path = self.base_dir / "orders.json"
        self.export_dir = self.base_dir / "order_exports"

    def append_many(
        self,
        task_context: TaskContext,
        deliveries: tuple[PipelineBatchDelivery, ...] | list[PipelineBatchDelivery],
    ) -> None:
        if not deliveries:
            return

        records = self._load_records()
        for delivery in deliveries:
            for order_line in delivery.batch.order_lines:
                records.append(
                    _order_to_dict(
                        StoredSpecialPushOrder(
                            trace_id=task_context.trace_id,
                            temp_push_id=self.temp_push_id,
                            group_name=delivery.batch.group_name,
                            owner_mobile=delivery.batch.owner_mobile,
                            order_no=order_line.order_no,
                            delivery_order_no=order_line.delivery_order_no,
                            warehouse_code=order_line.warehouse_code,
                            warehouse_name=order_line.warehouse_name,
                            sku_code=order_line.sku_code,
                            goods_summary=order_line.goods_summary,
                            quantity=order_line.quantity,
                            receiver_name=order_line.receiver_name,
                            address=order_line.address,
                            phone=order_line.phone,
                            logistics_company=order_line.logistics_company,
                            logistics_no=order_line.logistics_no,
                            file_path=str(delivery.generated_file.file_path),
                            message_tracking_id=delivery.message_result.tracking_id,
                        )
                    )
                )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_by_trace(self, trace_id: str) -> tuple[StoredSpecialPushOrder, ...]:
        normalized = _normalize_trace_id(trace_id)
        return tuple(
            _stored_from_dict(record)
            for record in self._load_records()
            if record.get("trace_id") == normalized
        )

    def list_all(self) -> tuple[StoredSpecialPushOrder, ...]:
        return tuple(_stored_from_dict(r) for r in self._load_records())

    def export_csv(self, trace_id: str) -> Path:
        normalized = _normalize_trace_id(trace_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.export_dir / (
            f"temp_push_{_safe_name(self.temp_push_id)}_{_safe_name(normalized)}_{datetime.now():%Y%m%d%H%M%S}.csv"
        )
        rows = [_csv_row(r) for r in self.list_by_trace(normalized)]

        with file_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(SPECIAL_PUSH_ORDER_CSV_HEADERS)
            writer.writerows(rows)

        return file_path

    def _load_records(self) -> list[dict[str, object]]:
        if not self.history_path.exists():
            return []
        data = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("special push order history must be a list")
        return [item for item in data if isinstance(item, dict)]


def _order_to_dict(record: StoredSpecialPushOrder) -> dict[str, object]:
    return {
        "trace_id": record.trace_id,
        "temp_push_id": record.temp_push_id,
        "group_name": record.group_name,
        "owner_mobile": record.owner_mobile,
        "order_no": record.order_no,
        "delivery_order_no": record.delivery_order_no,
        "warehouse_code": record.warehouse_code,
        "warehouse_name": record.warehouse_name,
        "sku_code": record.sku_code,
        "goods_summary": record.goods_summary,
        "quantity": record.quantity,
        "receiver_name": record.receiver_name,
        "address": record.address,
        "phone": record.phone,
        "logistics_company": record.logistics_company,
        "logistics_no": record.logistics_no,
        "file_path": record.file_path,
        "message_tracking_id": record.message_tracking_id,
    }


def _stored_from_dict(data: dict[str, Any]) -> StoredSpecialPushOrder:
    return StoredSpecialPushOrder(
        trace_id=_required_string(data, "trace_id"),
        temp_push_id=_optional_string(data, "temp_push_id"),
        group_name=_optional_string(data, "group_name"),
        owner_mobile=_optional_string(data, "owner_mobile"),
        order_no=_required_string(data, "order_no"),
        delivery_order_no=_required_string(data, "delivery_order_no"),
        warehouse_code=_optional_string(data, "warehouse_code"),
        warehouse_name=_optional_string(data, "warehouse_name"),
        sku_code=_required_string(data, "sku_code"),
        goods_summary=_required_string(data, "goods_summary"),
        quantity=_non_negative_int(data, "quantity"),
        receiver_name=_required_string(data, "receiver_name"),
        address=_required_string(data, "address"),
        phone=_required_string(data, "phone"),
        logistics_company=_optional_string(data, "logistics_company"),
        logistics_no=_optional_string(data, "logistics_no"),
        file_path=_optional_string(data, "file_path"),
        message_tracking_id=_optional_string(data, "message_tracking_id"),
    )


def _csv_row(record: StoredSpecialPushOrder) -> list[object]:
    return [
        record.trace_id,
        record.temp_push_id,
        record.group_name,
        record.owner_mobile,
        record.order_no,
        record.delivery_order_no,
        record.warehouse_code,
        record.warehouse_name,
        record.sku_code,
        record.goods_summary,
        record.quantity,
        record.receiver_name,
        record.address,
        record.phone,
        record.logistics_company,
        record.logistics_no,
        record.file_path,
        record.message_tracking_id,
    ]


def _normalize_trace_id(trace_id: str) -> str:
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")
    return trace_id.strip()


def _safe_name(value: str) -> str:
    safe_value = sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe_value or "trace"


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


def _non_negative_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value
