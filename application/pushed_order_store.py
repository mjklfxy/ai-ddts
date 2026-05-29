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
from infrastructure.cloud_warehouse_client import CloudWarehouseClient


PUSHED_ORDER_CSV_HEADERS = (
    "trace_id",
    "任务名称",
    "推送群",
    "群主手机号",
    "供应商名称",
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
    "渠道分类",
    "推送文件",
    "消息追踪号",
)


@dataclass(frozen=True, slots=True)
class StoredPushedOrder:
    """Persisted normal pushed order detail attached to one task run."""

    trace_id: str
    task_id: str
    task_name: str
    group_name: str
    owner_mobile: str
    supplier_name: str
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
    channel_classification: str
    file_path: str
    message_tracking_id: str


class PushedOrderStore:
    """Persists normal pushed order details and exports them as CSV."""

    def __init__(
        self,
        history_path: str | Path = Path("outputs") / "pushed_orders.json",
        export_dir: str | Path = Path("outputs") / "pushed_order_exports",
    ) -> None:
        self.history_path = Path(history_path)
        self.export_dir = Path(export_dir)

    def append_many(
        self,
        task_context: TaskContext,
        deliveries: tuple[PipelineBatchDelivery, ...] | list[PipelineBatchDelivery],
        supplier_client: CloudWarehouseClient | None = None,
    ) -> None:
        """Appends normal pushed order details for one task run."""

        if not deliveries:
            return

        records = self._load_records()
        for delivery in deliveries:
            for order_line in delivery.batch.order_lines:
                supplier_name = (
                    supplier_client.get_supplier(order_line.sku_code.strip())
                    if supplier_client
                    else ""
                )
                records.append(
                    pushed_order_to_dict(
                        _stored_from_delivery(
                            task_context=task_context,
                            delivery=delivery,
                            order_line=order_line,
                            supplier_name=supplier_name or "",
                        )
                    )
                )
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_by_trace(self, trace_id: str) -> tuple[StoredPushedOrder, ...]:
        """Returns normal pushed order details for one task trace id."""

        normalized_trace_id = _normalize_trace_id(trace_id)
        return tuple(
            _stored_from_dict(record)
            for record in self._load_records()
            if record.get("trace_id") == normalized_trace_id
        )

    def export_csv(self, trace_id: str) -> Path:
        """Exports normal pushed order details for one task trace id."""

        normalized_trace_id = _normalize_trace_id(trace_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.export_dir / (
            f"pushed_orders_{_safe_name(normalized_trace_id)}_{datetime.now():%Y%m%d%H%M%S}.csv"
        )
        rows = [_csv_row(record) for record in self.list_by_trace(normalized_trace_id)]

        with file_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(PUSHED_ORDER_CSV_HEADERS)
            writer.writerows(rows)

        return file_path

    def _load_records(self) -> list[dict[str, object]]:
        """Loads raw pushed order records from local JSON history."""

        if not self.history_path.exists():
            return []

        data = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("pushed order history must be a list")

        records: list[dict[str, object]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("pushed order history items must be objects")
            records.append(item)
        return records


def pushed_order_to_dict(record: StoredPushedOrder) -> dict[str, object]:
    """Converts a stored pushed order into JSON-compatible data."""

    return {
        "trace_id": record.trace_id,
        "task_id": record.task_id,
        "task_name": record.task_name,
        "group_name": record.group_name,
        "owner_mobile": record.owner_mobile,
        "supplier_name": record.supplier_name,
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
        "channel_classification": record.channel_classification,
        "file_path": record.file_path,
        "message_tracking_id": record.message_tracking_id,
    }


def _stored_from_delivery(
    task_context: TaskContext,
    delivery: PipelineBatchDelivery,
    order_line,
    supplier_name: str = "",
) -> StoredPushedOrder:
    return StoredPushedOrder(
        trace_id=task_context.trace_id,
        task_id=task_context.task_id,
        task_name=task_context.task_name,
        group_name=delivery.batch.group_name,
        owner_mobile=delivery.batch.owner_mobile,
        supplier_name=supplier_name,
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
        channel_classification=order_line.channel_classification,
        file_path=str(delivery.generated_file.file_path),
        message_tracking_id=delivery.message_result.tracking_id,
    )


def _stored_from_dict(data: dict[str, Any]) -> StoredPushedOrder:
    return StoredPushedOrder(
        trace_id=_required_string(data, "trace_id"),
        task_id=_required_string(data, "task_id"),
        task_name=_required_string(data, "task_name"),
        group_name=_required_string(data, "group_name"),
        owner_mobile=_optional_string(data, "owner_mobile"),
        supplier_name=_optional_string(data, "supplier_name"),
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
        channel_classification=_optional_string(data, "channel_classification"),
        message_tracking_id=_optional_string(data, "message_tracking_id"),
    )


def _csv_row(record: StoredPushedOrder) -> list[object]:
    return [
        record.trace_id,
        record.task_name,
        record.group_name,
        record.owner_mobile,
        record.supplier_name,
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
        record.channel_classification,
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
