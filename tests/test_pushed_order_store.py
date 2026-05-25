import csv
import json
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.file_generator import GeneratedFile
from application.order_splitter import GroupOrderBatch, OrderLineForSplit
from application.pipeline import PipelineBatchDelivery
from application.pushed_order_store import PushedOrderStore, StoredPushedOrder
from application.task_service import TaskService
from infrastructure.message_adapter import MessageSendResult


class _FakeSupplierClient:
    """Minimal supplier client stub for pushed order store tests."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def get_supplier(self, sku_name: str) -> str | None:
        return self._mapping.get(sku_name)


class PushedOrderStoreTests(TestCase):
    """Tests normal pushed order detail persistence and CSV export."""

    def test_append_many_persists_supplier_enriched_order_lines(self) -> None:
        history_path = Path("tmp") / "test_pushed_order_store" / "history.json"
        if history_path.exists():
            history_path.unlink()
        store = PushedOrderStore(history_path=history_path)

        store.append_many(
            task_context=make_task(),
            deliveries=[make_delivery()],
            supplier_client=_FakeSupplierClient({"羊奶粉": "供应商A"}),
        )

        records = PushedOrderStore(history_path=history_path).list_by_trace("TRACE-001")
        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], StoredPushedOrder)
        self.assertEqual(records[0].sku_code, "羊奶粉")
        self.assertEqual(records[0].supplier_name, "供应商A")
        persisted = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted[0]["supplier_name"], "供应商A")
        self.assertNotIn("supplier_code", persisted[0])

    def test_export_csv_writes_only_requested_trace_id(self) -> None:
        history_path = Path("tmp") / "test_pushed_order_store" / "export_history.json"
        export_dir = Path("tmp") / "test_pushed_order_store" / "exports"
        if history_path.exists():
            history_path.unlink()
        store = PushedOrderStore(history_path=history_path, export_dir=export_dir)
        store.append_many(
            task_context=make_task(trace_id="TRACE-001"),
            deliveries=[make_delivery(order_no="SO-001")],
        )
        store.append_many(
            task_context=make_task(trace_id="TRACE-002"),
            deliveries=[make_delivery(order_no="SO-002")],
        )

        file_path = store.export_csv("TRACE-002")

        with file_path.open(newline="", encoding="utf-8-sig") as file:
            rows = list(csv.reader(file))
        self.assertEqual(rows[0][4], "供应商名称")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TRACE-002")
        self.assertEqual(rows[1][5], "SO-002")
        self.assertEqual(rows[1][9], "羊奶粉")


def make_task(trace_id: str = "TRACE-001"):
    """Builds a deterministic task context for pushed order store tests."""

    return TaskService(
        trace_id_generator=lambda: trace_id,
        clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
    ).create_task(
        task_name="daily-direct-order",
        window_start=datetime(2026, 4, 30, 8, 0, 0),
        window_end=datetime(2026, 4, 30, 12, 0, 0),
    )


def make_delivery(order_no: str = "SO-001") -> PipelineBatchDelivery:
    """Builds one successful pushed delivery for store tests."""

    order_line = OrderLineForSplit(
        order_no=order_no,
        sku_code="羊奶粉",
        delivery_order_no=f"DO-{order_no}",
        goods_summary="羊奶粉",
        quantity=2,
        receiver_name="Receiver",
        address="Address",
        phone="13800000000",
        logistics_company="SF",
        logistics_no=f"SF-{order_no}",
        warehouse_code="WH-001",
        warehouse_name="华东仓",
    )
    return PipelineBatchDelivery(
        batch=GroupOrderBatch(
            group_name="GROUP-A",
            owner_mobile="",
            user_id="",
            order_lines=(order_line,),
        ),
        generated_file=GeneratedFile(
            group_name="GROUP-A",
            file_path=Path("tmp") / "GROUP-A.xlsx",
            row_count=1,
        ),
        message_result=MessageSendResult(
            trace_id="TRACE-001",
            group_name="GROUP-A",
            tracking_id="MSG-001",
            attempts=1,
        ),
    )
