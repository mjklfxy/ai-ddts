from datetime import datetime
from unittest import TestCase

from application.task_service import TaskContext, TaskService
from domain.enums.status import KingdeeStatus, PaymentStatus, PushStatus


class TaskServiceTests(TestCase):
    """Tests task creation with trace id and initial statuses."""

    def test_create_task_uses_injected_trace_id_and_initial_statuses(self) -> None:
        service = TaskService(
            trace_id_generator=lambda: "TRACE-001",
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
        )

        task = service.create_task(
            task_name="daily-direct-order",
            window_start=datetime(2026, 4, 30, 8, 0, 0),
            window_end=datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertIsInstance(task, TaskContext)
        self.assertEqual(task.task_id, "TRACE-001")
        self.assertEqual(task.trace_id, "TRACE-001")
        self.assertEqual(task.created_at, datetime(2026, 4, 30, 12, 0, 0))
        self.assertEqual(task.push_status, PushStatus.PENDING)
        self.assertEqual(task.push_status.value, "待推送")
        self.assertEqual(task.payment_status, PaymentStatus.UNPAID)
        self.assertEqual(task.payment_status.value, "未付款")
        self.assertEqual(task.kingdee_status, KingdeeStatus.PENDING)
        self.assertEqual(task.kingdee_status.value, "采购申请单待提交")

    def test_default_task_code_uses_date_and_daily_sequence(self) -> None:
        service = TaskService(
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
        )

        task = service.create_task(
            task_name="daily-direct-order",
            window_start=datetime(2026, 4, 30, 8, 0, 0),
            window_end=datetime(2026, 4, 30, 12, 0, 0),
        )
        second_task = service.create_task(
            task_name="daily-direct-order",
            window_start=datetime(2026, 4, 30, 8, 0, 0),
            window_end=datetime(2026, 4, 30, 12, 0, 0),
        )

        # === MODIFIED START ===
        # 原因：任务批次编码规则改为 yyyyMMdd + 四位数日内累计。
        # 影响范围：TaskService 默认编码生成测试。
        self.assertEqual(task.trace_id, "202604300001")
        self.assertEqual(second_task.trace_id, "202604300002")
        # === MODIFIED END ===
        self.assertEqual(task.task_id, task.trace_id)
