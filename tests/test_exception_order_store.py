import csv
import json
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.exception_order_store import ExceptionOrderStore, StoredExceptionOrder
from application.task_service import TaskService
from domain.enums.exception import ExceptionProcessStatus
from domain.exception_order import ExceptionOrder


class ExceptionOrderStoreTests(TestCase):
    """Tests exception order persistence and CSV export."""

    def test_missing_history_returns_empty_items(self) -> None:
        store = ExceptionOrderStore(
            history_path=Path("tmp") / "test_exception_order_store" / "missing.json"
        )

        self.assertEqual(store.list_recent(), ())

    def test_append_many_persists_and_lists_recent_records(self) -> None:
        history_path = Path("tmp") / "test_exception_order_store" / "history.json"
        if history_path.exists():
            history_path.unlink()
        store = ExceptionOrderStore(history_path=history_path)

        store.append_many(
            task_context=make_task(),
            exception_orders=[make_exception_order("SO-001"), make_exception_order("SO-002")],
        )

        records = ExceptionOrderStore(history_path=history_path).list_recent(limit=2)
        self.assertEqual([record.order_no for record in records], ["SO-002", "SO-001"])
        self.assertIsInstance(records[0], StoredExceptionOrder)
        self.assertEqual(records[0].trace_id, "TRACE-001")
        self.assertEqual(records[0].sku_code, "SKU-001")
        # === MODIFIED START ===
        # 原因：异常订单持久化新增仓库字段。
        # 影响范围：异常订单 store 测试。
        self.assertEqual(records[0].warehouse_name, "华东仓")
        # === MODIFIED END ===
        persisted = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted[0]["process_status"], ExceptionProcessStatus.PENDING.value)
        self.assertEqual(persisted[0]["warehouse_name"], "华东仓")

    def test_export_csv_writes_exception_orders(self) -> None:
        history_path = Path("tmp") / "test_exception_order_store" / "export_history.json"
        export_dir = Path("tmp") / "test_exception_order_store" / "exports"
        if history_path.exists():
            history_path.unlink()
        store = ExceptionOrderStore(history_path=history_path, export_dir=export_dir)
        store.append_many(task_context=make_task(), exception_orders=[make_exception_order("SO-001", supplier_name="供应商A")])

        file_path = store.export_csv()

        with file_path.open(newline="", encoding="utf-8-sig") as file:
            rows = list(csv.reader(file))
        self.assertEqual(rows[0][2], "关联单号")
        self.assertEqual(rows[1][2], "SO-001")
        self.assertEqual(rows[0][4], "仓库编码")
        self.assertEqual(rows[0][6], "SKU（商品名称）")
        self.assertEqual(rows[0][7], "供应商名称")
        self.assertEqual(rows[1][5], "华东仓")
        self.assertEqual(rows[1][6], "SKU-001")
        self.assertEqual(rows[1][7], "供应商A")
        self.assertEqual(rows[1][18], "未配置推送群")

    # === MODIFIED START ===
    # 原因：任务清单异常订单下载需要支持按任务批次筛选。
    # 影响范围：ExceptionOrderStore.export_csv。
    def test_export_csv_can_filter_by_trace_id(self) -> None:
        history_path = Path("tmp") / "test_exception_order_store" / "trace_export_history.json"
        export_dir = Path("tmp") / "test_exception_order_store" / "trace_exports"
        if history_path.exists():
            history_path.unlink()
        store = ExceptionOrderStore(history_path=history_path, export_dir=export_dir)
        store.append_many(task_context=make_task(trace_id="TRACE-001"), exception_orders=[make_exception_order("SO-001")])
        store.append_many(task_context=make_task(trace_id="TRACE-002"), exception_orders=[make_exception_order("SO-002")])

        file_path = store.export_csv(trace_id="TRACE-002")

        with file_path.open(newline="", encoding="utf-8-sig") as file:
            rows = list(csv.reader(file))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TRACE-002")
        self.assertEqual(rows[1][2], "SO-002")
    # === MODIFIED END ===

    def test_invalid_limit_is_rejected(self) -> None:
        store = ExceptionOrderStore(
            history_path=Path("tmp") / "test_exception_order_store" / "missing.json"
        )

        with self.assertRaisesRegex(ValueError, "limit"):
            store.list_recent(limit=0)


def make_task(trace_id: str = "TRACE-001"):
    """Builds a deterministic task context for exception order store tests."""

    return TaskService(
        trace_id_generator=lambda: trace_id,
        clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
    ).create_task(
        task_name="daily-direct-order",
        window_start=datetime(2026, 4, 30, 8, 0, 0),
        window_end=datetime(2026, 4, 30, 12, 0, 0),
    )


def make_exception_order(order_no: str, supplier_name: str = "") -> ExceptionOrder:
    """Builds one exception order for persistence tests."""

    return ExceptionOrder(
        order_no=order_no,
        sku_code="SKU-001",
        delivery_order_no=f"DO-{order_no}",
        goods_summary="Goods SKU-001",
        # === MODIFIED START ===
        # 原因：异常订单测试数据新增仓库字段。
        # 影响范围：异常订单持久化测试。
        warehouse_code="WH-001",
        warehouse_name="华东仓",
        # === MODIFIED END ===
        quantity=1,
        receiver_name="Receiver",
        address="Address",
        phone="13800000000",
        logistics_company="SF",
        logistics_no=f"SF-{order_no}",
        # === MODIFIED START ===
        # 原因：SkuServiceRule 已改为 IGNORE，异常订单持久化示例改用 GroupRule。
        # 影响范围：异常订单 store 测试数据。
        reason="未配置推送群",
        rule_name="GroupRule",
        supplier_name=supplier_name,
        # === MODIFIED END ===
    )
