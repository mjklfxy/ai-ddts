from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import sub
from typing import Any

from application.task_service import TaskContext
from domain.enums.exception import ExceptionProcessStatus
from domain.exception_order import ExceptionOrder
from infrastructure.cloud_warehouse_client import CloudWarehouseClient
from shared.env import is_channel_classification_enabled


def get_exception_order_csv_headers() -> list[str]:
    """Returns CSV headers, conditionally including channel_classification."""
    headers = [
        "trace_id",
        "任务名称",
        "关联单号",
        "发货单号",
        "仓库编码",
        "仓库",
        "SKU（商品名称）",
        "供应商名称",
        "推送群名称",
        "群主手机号",
    ]
    if is_channel_classification_enabled():
        headers.append("渠道分类")
    headers.extend([
        "货品摘要",
        "数量",
        "收件人",
        "地址",
        "电话",
        "物流公司",
        "物流单号",
        "异常原因",
        "规则名称",
        "处理状态",
    ])
    return headers


# Backward-compatible alias evaluated at import time.
EXCEPTION_ORDER_CSV_HEADERS: tuple[str, ...] = tuple(get_exception_order_csv_headers())


@dataclass(frozen=True, slots=True)
class StoredExceptionOrder:
    """Persisted exception order detail attached to one task run."""

    trace_id: str
    task_id: str
    task_name: str
    order_no: str
    sku_code: str
    delivery_order_no: str
    goods_summary: str
    # === MODIFIED START ===
    # 原因：异常订单持久化需要保留抓单时的仓库字段。
    # 影响范围：StoredExceptionOrder、API payload 和 CSV。
    warehouse_code: str
    warehouse_name: str
    # === MODIFIED END ===
    quantity: int
    receiver_name: str
    address: str
    phone: str
    logistics_company: str
    logistics_no: str
    # === MODIFIED START ===
    # 原因：异常订单持久化需要保留推送群和供应商信息，供接口查询和下载。
    # 影响范围：StoredExceptionOrder、JSON/CSV 序列化。
    group_name: str
    owner_mobile: str
    supplier_name: str
    # === MODIFIED END ===
    reason: str
    rule_name: str
    channel_classification: str = ""
    process_status: ExceptionProcessStatus = ExceptionProcessStatus.PENDING


class ExceptionOrderStore:
    """Persists exception orders and exports them for manual processing."""

    def __init__(
        self,
        history_path: str | Path = Path("outputs") / "exception_orders.json",
        export_dir: str | Path = Path("outputs") / "exception_order_exports",
    ) -> None:
        self.history_path = Path(history_path)
        self.export_dir = Path(export_dir)

    def append_many(
        self,
        task_context: TaskContext,
        exception_orders: tuple[ExceptionOrder, ...] | list[ExceptionOrder],
    ) -> None:
        """Appends exception order details for one task run."""

        if not exception_orders:
            return

        records = self._load_records()
        records.extend(
            stored_exception_to_dict(_stored_from_exception(task_context, exception_order))
            for exception_order in exception_orders
        )
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_recent(self, limit: int = 100) -> tuple[StoredExceptionOrder, ...]:
        """Returns recent exception orders from newest to oldest."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")

        records = self._load_records()
        recent_records = records[-limit:]
        return tuple(_stored_from_dict(record) for record in reversed(recent_records))

    # === MODIFIED START ===
    # 原因：任务清单需要区分下载当前批次异常订单，并按 SKU-供应商对照补充供应商字段。
    # 影响范围：异常订单 CSV 导出。
    def export_csv(
        self,
        trace_id: str | None = None,
        supplier_client: CloudWarehouseClient | None = None,
    ) -> Path:
        """Exports persisted exception orders to a CSV file."""

        normalized_trace_id = _optional_trace_id(trace_id)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        file_name = "exception_orders"
        if normalized_trace_id is not None:
            file_name = f"{file_name}_{_safe_name(normalized_trace_id)}"
        file_path = self.export_dir / f"{file_name}_{datetime.now():%Y%m%d%H%M%S}.csv"
        rows: list[list[object]] = []
        for record in self._load_records():
            if normalized_trace_id is not None and record.get("trace_id") != normalized_trace_id:
                continue
            stored = _stored_from_dict(record)
            # === MODIFIED START ===
            # 原因：保留 supplier_client 兜底，兼容旧记录没有 supplier_name 字段。
            # 影响范围：旧异常订单 CSV 导出。
            if not stored.supplier_name and supplier_client:
                stored = StoredExceptionOrder(
                    trace_id=stored.trace_id,
                    task_id=stored.task_id,
                    task_name=stored.task_name,
                    order_no=stored.order_no,
                    sku_code=stored.sku_code,
                    delivery_order_no=stored.delivery_order_no,
                    goods_summary=stored.goods_summary,
                    warehouse_code=stored.warehouse_code,
                    warehouse_name=stored.warehouse_name,
                    quantity=stored.quantity,
                    receiver_name=stored.receiver_name,
                    address=stored.address,
                    phone=stored.phone,
                    logistics_company=stored.logistics_company,
                    logistics_no=stored.logistics_no,
                    group_name=stored.group_name,
                    owner_mobile=stored.owner_mobile,
                    supplier_name=supplier_client.get_supplier(stored.sku_code) or "",
                    reason=stored.reason,
                    rule_name=stored.rule_name,
                    process_status=stored.process_status,
                )
            # === MODIFIED END ===
            rows.append(_csv_row(stored))

        with file_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(get_exception_order_csv_headers())
            writer.writerows(rows)

        return file_path
    # === MODIFIED END ===

    def _load_records(self) -> list[dict[str, object]]:
        """Loads raw exception order records from local JSON history."""

        if not self.history_path.exists():
            return []

        data = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("exception order history must be a list")

        records: list[dict[str, object]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("exception order history items must be objects")
            records.append(item)
        return records


def stored_exception_to_dict(record: StoredExceptionOrder) -> dict[str, object]:
    """Converts a stored exception order into JSON-compatible data."""

    return {
        "trace_id": record.trace_id,
        "task_id": record.task_id,
        "task_name": record.task_name,
        "order_no": record.order_no,
        "sku_code": record.sku_code,
        "delivery_order_no": record.delivery_order_no,
        "goods_summary": record.goods_summary,
        # === MODIFIED START ===
        # 原因：异常订单接口和导出需要返回仓库字段。
        # 影响范围：exception_orders_to_payload 和落盘 JSON。
        "warehouse_code": record.warehouse_code,
        "warehouse_name": record.warehouse_name,
        # === MODIFIED END ===
        "quantity": record.quantity,
        "receiver_name": record.receiver_name,
        "address": record.address,
        "phone": record.phone,
        "logistics_company": record.logistics_company,
        "logistics_no": record.logistics_no,
        # === MODIFIED START ===
        # 原因：接口和落盘 JSON 需要带出推送群和供应商信息。
        # 影响范围：exception_orders.json 与 API 响应。
        "group_name": record.group_name,
        "owner_mobile": record.owner_mobile,
        "supplier_name": record.supplier_name,
        "channel_classification": record.channel_classification,
        # === MODIFIED END ===
        "reason": record.reason,
        "rule_name": record.rule_name,
        "process_status": record.process_status.value,
    }


def exception_orders_to_payload(records: tuple[StoredExceptionOrder, ...]) -> dict[str, object]:
    """Converts stored exception orders into an API response payload."""

    return {
        "items": [stored_exception_to_dict(record) for record in records],
    }


def _stored_from_exception(
    task_context: TaskContext,
    exception_order: ExceptionOrder,
) -> StoredExceptionOrder:
    return StoredExceptionOrder(
        trace_id=task_context.trace_id,
        task_id=task_context.task_id,
        task_name=task_context.task_name,
        order_no=exception_order.order_no,
        sku_code=exception_order.sku_code,
        delivery_order_no=exception_order.delivery_order_no,
        goods_summary=exception_order.goods_summary,
        # === MODIFIED START ===
        # 原因：从异常订单明细保留仓库字段。
        # 影响范围：异常订单持久化。
        warehouse_code=exception_order.warehouse_code,
        warehouse_name=exception_order.warehouse_name,
        # === MODIFIED END ===
        quantity=exception_order.quantity,
        receiver_name=exception_order.receiver_name,
        address=exception_order.address,
        phone=exception_order.phone,
        logistics_company=exception_order.logistics_company,
        logistics_no=exception_order.logistics_no,
        # === MODIFIED START ===
        # 原因：从异常订单保留推送群和供应商字段到持久化记录。
        # 影响范围：exception_orders.json 落盘。
        group_name=exception_order.group_name,
        owner_mobile=exception_order.owner_mobile,
        supplier_name=exception_order.supplier_name,
        channel_classification=exception_order.channel_classification,
        # === MODIFIED END ===
        reason=exception_order.reason,
        rule_name=exception_order.rule_name,
        process_status=exception_order.process_status,
    )


def _stored_from_dict(data: dict[str, Any]) -> StoredExceptionOrder:
    return StoredExceptionOrder(
        trace_id=_required_string(data, "trace_id"),
        task_id=_required_string(data, "task_id"),
        task_name=_required_string(data, "task_name"),
        order_no=_required_string(data, "order_no"),
        sku_code=_required_string(data, "sku_code"),
        delivery_order_no=_required_string(data, "delivery_order_no"),
        goods_summary=_required_string(data, "goods_summary"),
        # === MODIFIED START ===
        # 原因：兼容旧历史记录没有仓库字段，同时新记录需要带出仓库。
        # 影响范围：异常订单历史读取。
        warehouse_code=_optional_string(data, "warehouse_code"),
        warehouse_name=_optional_string(data, "warehouse_name"),
        # === MODIFIED END ===
        quantity=_non_negative_int(data, "quantity"),
        receiver_name=_required_string(data, "receiver_name"),
        address=_required_string(data, "address"),
        phone=_required_string(data, "phone"),
        logistics_company=_optional_string(data, "logistics_company"),
        logistics_no=_optional_string(data, "logistics_no"),
        # === MODIFIED START ===
        # 原因：兼容旧记录没有推送群和供应商字段，缺失时默认空字符串。
        # 影响范围：异常订单历史读取与接口查询。
        group_name=_optional_string(data, "group_name"),
        owner_mobile=_optional_string(data, "owner_mobile"),
        supplier_name=_optional_string(data, "supplier_name"),
        channel_classification=_optional_string(data, "channel_classification"),
        # === MODIFIED END ===
        reason=_required_string(data, "reason"),
        rule_name=_required_string(data, "rule_name"),
        process_status=_process_status(data.get("process_status")),
    )


def _csv_row(record: StoredExceptionOrder) -> list[object]:
    row = [
        record.trace_id,
        record.task_name,
        record.order_no,
        record.delivery_order_no,
        record.warehouse_code,
        record.warehouse_name,
        record.sku_code,
        record.supplier_name,
        record.group_name,
        record.owner_mobile,
    ]
    if is_channel_classification_enabled():
        row.append(record.channel_classification)
    row.extend([
        record.goods_summary,
        record.quantity,
        record.receiver_name,
        record.address,
        record.phone,
        record.logistics_company,
        record.logistics_no,
        record.reason,
        record.rule_name,
        record.process_status.value,
    ])
    return row


# === MODIFIED START ===
# 原因：异常订单下载支持按任务批次筛选并生成安全文件名。
# 影响范围：ExceptionOrderStore.export_csv。
def _optional_trace_id(trace_id: str | None) -> str | None:
    if trace_id is None:
        return None
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")
    return trace_id.strip()


def _safe_name(value: str) -> str:
    safe_value = sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe_value or "trace"
# === MODIFIED END ===


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


def _process_status(value: Any) -> ExceptionProcessStatus:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("process_status must be a non-empty string")

    for status in ExceptionProcessStatus:
        if status.value == value:
            return status
    raise ValueError(f"Unsupported exception process_status: {value}")
