import json
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.payment_receipt_store import PaymentReceiptRecord, PaymentReceiptStore
from domain.enums.status import PaymentStatus


class PaymentReceiptStoreTests(TestCase):
    """Tests payment receipt persistence and status derivation."""

    def test_missing_receipt_returns_unpaid_status(self) -> None:
        store = PaymentReceiptStore(
            history_path=Path("tmp") / "test_payment_receipt_store" / "missing.json"
        )

        self.assertEqual(store.get_status("TRACE-001"), PaymentStatus.UNPAID)
        self.assertEqual(store.to_payload("TRACE-001")["payment_status"], "未付款")

    def test_save_receipt_persists_paid_record_and_file(self) -> None:
        history_path = Path("tmp") / "test_payment_receipt_store" / "history.json"
        receipt_dir = Path("tmp") / "test_payment_receipt_store" / "receipts"
        if history_path.exists():
            history_path.unlink()
        store = PaymentReceiptStore(
            history_path=history_path,
            receipt_dir=receipt_dir,
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
        )

        record = store.save_receipt(
            trace_id="TRACE-001",
            original_filename="../receipt image.png",
            content=b"receipt-bytes",
        )

        self.assertIsInstance(record, PaymentReceiptRecord)
        self.assertEqual(record.payment_status, PaymentStatus.PAID)
        self.assertEqual(record.original_filename, "receipt_image.png")
        self.assertTrue(record.receipt_file_path.exists())
        self.assertEqual(record.receipt_file_path.read_bytes(), b"receipt-bytes")
        self.assertEqual(store.get_status("TRACE-001"), PaymentStatus.PAID)
        persisted = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted[0]["payment_status"], "已付款")

    def test_empty_file_is_rejected(self) -> None:
        store = PaymentReceiptStore(
            history_path=Path("tmp") / "test_payment_receipt_store" / "empty.json"
        )

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            store.save_receipt(
                trace_id="TRACE-001",
                original_filename="receipt.png",
                content=b"",
            )

    def test_invalid_history_shape_is_rejected(self) -> None:
        history_path = Path("tmp") / "test_payment_receipt_store" / "invalid.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps({"trace_id": "TRACE-001"}), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "payment receipt history must be a list"):
            PaymentReceiptStore(history_path=history_path).get_status("TRACE-001")
