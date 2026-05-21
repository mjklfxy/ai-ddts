from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from domain.enums.status import PaymentStatus


@dataclass(frozen=True, slots=True)
class PaymentReceiptRecord:
    """Payment receipt record attached to one task trace."""

    trace_id: str
    payment_status: PaymentStatus
    original_filename: str
    receipt_file_path: Path
    uploaded_at: str


class PaymentReceiptStore:
    """Persists uploaded payment receipts and derives payment status."""

    def __init__(
        self,
        history_path: str | Path = Path("outputs") / "payment_receipts.json",
        receipt_dir: str | Path = Path("outputs") / "payment_receipts",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.history_path = Path(history_path)
        self.receipt_dir = Path(receipt_dir)
        self.clock = clock or datetime.now

    def save_receipt(
        self,
        trace_id: str,
        original_filename: str,
        content: bytes,
    ) -> PaymentReceiptRecord:
        """Stores an uploaded payment receipt and marks the task as paid."""

        safe_trace_id = _required_string(trace_id, "trace_id")
        safe_filename = _safe_filename(original_filename)
        if not content:
            raise ValueError("payment receipt file must not be empty")

        uploaded_at = self.clock().isoformat()
        task_dir = self.receipt_dir / _safe_path_part(safe_trace_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        receipt_file_path = task_dir / f"{_safe_path_part(uploaded_at)}_{safe_filename}"
        receipt_file_path.write_bytes(content)

        record = PaymentReceiptRecord(
            trace_id=safe_trace_id,
            payment_status=PaymentStatus.PAID,
            original_filename=safe_filename,
            receipt_file_path=receipt_file_path,
            uploaded_at=uploaded_at,
        )
        self._upsert(record)
        return record

    def get_record(self, trace_id: str) -> PaymentReceiptRecord | None:
        """Returns the latest payment receipt record for a task."""

        safe_trace_id = _required_string(trace_id, "trace_id")
        records = [
            _record_from_dict(item)
            for item in self._load_records()
            if item.get("trace_id") == safe_trace_id
        ]
        if not records:
            return None
        return records[-1]

    def get_status(self, trace_id: str) -> PaymentStatus:
        """Returns paid when a receipt exists, otherwise unpaid."""

        if self.get_record(trace_id) is None:
            return PaymentStatus.UNPAID
        return PaymentStatus.PAID

    def to_payload(self, trace_id: str) -> dict[str, object]:
        """Builds API-safe payment status payload for one task."""

        record = self.get_record(trace_id)
        if record is None:
            return {
                "trace_id": _required_string(trace_id, "trace_id"),
                "payment_status": PaymentStatus.UNPAID.value,
                "original_filename": None,
                "receipt_file_path": None,
                "uploaded_at": None,
            }

        return payment_receipt_to_dict(record)

    def _upsert(self, record: PaymentReceiptRecord) -> None:
        """Appends the latest payment receipt record to local history."""

        records = self._load_records()
        records.append(payment_receipt_to_dict(record))
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_records(self) -> list[dict[str, object]]:
        """Loads raw payment receipt records from local JSON history."""

        if not self.history_path.exists():
            return []

        data = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("payment receipt history must be a list")

        records: list[dict[str, object]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("payment receipt history items must be objects")
            records.append(item)
        return records


def payment_receipt_to_dict(record: PaymentReceiptRecord) -> dict[str, object]:
    """Converts a payment receipt record into JSON-compatible data."""

    return {
        "trace_id": record.trace_id,
        "payment_status": record.payment_status.value,
        "original_filename": record.original_filename,
        "receipt_file_path": str(record.receipt_file_path),
        "uploaded_at": record.uploaded_at,
    }


def _record_from_dict(data: dict[str, Any]) -> PaymentReceiptRecord:
    return PaymentReceiptRecord(
        trace_id=_required_string(data.get("trace_id"), "trace_id"),
        payment_status=_payment_status(data.get("payment_status")),
        original_filename=_required_string(data.get("original_filename"), "original_filename"),
        receipt_file_path=Path(_required_string(data.get("receipt_file_path"), "receipt_file_path")),
        uploaded_at=_required_string(data.get("uploaded_at"), "uploaded_at"),
    )


def _payment_status(value: Any) -> PaymentStatus:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("payment_status must be a non-empty string")

    for status in PaymentStatus:
        if status.value == value:
            return status
    raise ValueError(f"Unsupported payment_status: {value}")


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _safe_filename(filename: str) -> str:
    base_name = Path(filename.replace("\\", "/")).name.strip()
    if not base_name:
        raise ValueError("payment receipt filename must be a non-empty string")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name)
    return safe_name or "receipt"


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)
