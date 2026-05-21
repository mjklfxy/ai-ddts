import json
from pathlib import Path
from unittest import TestCase

from application.manual_runner import RunSummary
from application.task_run_store import TaskRunStore, run_summary_to_dict
from domain.enums.status import KingdeeStatus, PushStatus


class TaskRunStoreTests(TestCase):
    """Tests local persistence for task run summaries."""

    def test_missing_history_returns_no_latest_summary(self) -> None:
        store = TaskRunStore(history_path=Path("tmp") / "test_task_run_store" / "missing.json")

        self.assertIsNone(store.latest())
        self.assertEqual(store.list_recent(), ())

    def test_append_latest_and_list_recent_are_persisted(self) -> None:
        history_path = Path("tmp") / "test_task_run_store" / "history.json"
        if history_path.exists():
            history_path.unlink()
        store = TaskRunStore(history_path=history_path)

        first = make_summary("TRACE-001", passed_count=1)
        second = make_summary("TRACE-002", passed_count=2)
        store.append(first)
        store.append(second)

        reloaded_store = TaskRunStore(history_path=history_path)
        self.assertEqual(reloaded_store.latest(), second)
        self.assertEqual(reloaded_store.list_recent(limit=1), (second,))
        self.assertEqual(reloaded_store.list_recent(limit=2), (second, first))
        # === MODIFIED START ===
        # 原因：任务批次编码生成需要按历史写入顺序读取已用批次号。
        # 影响范围：TaskRunStore 批次号读取能力。
        self.assertEqual(reloaded_store.list_trace_ids(), ("TRACE-001", "TRACE-002"))
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务状态需要以中文 Enum 值稳定持久化。
        # 影响范围：任务历史 JSON 结构。
        persisted = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted[-1]["push_status"], "已推送")
        self.assertEqual(persisted[-1]["kingdee_status"], "采购申请单已提交")
        self.assertEqual(persisted[-1]["task_name"], "daily-direct-order")
        # === MODIFIED END ===

    def test_invalid_history_shape_is_rejected(self) -> None:
        history_path = Path("tmp") / "test_task_run_store" / "invalid.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps({"trace_id": "TRACE-001"}), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "task run history must be a list"):
            TaskRunStore(history_path=history_path).latest()

    def test_invalid_limit_is_rejected(self) -> None:
        store = TaskRunStore(history_path=Path("tmp") / "test_task_run_store" / "missing.json")

        with self.assertRaisesRegex(ValueError, "limit"):
            store.list_recent(limit=0)

    # === MODIFIED START ===
    # 原因：API 响应和持久化复用同一任务摘要序列化结构。
    # 影响范围：任务摘要序列化。
    def test_run_summary_to_dict_uses_enum_values(self) -> None:
        payload = run_summary_to_dict(
            RunSummary(
                trace_id="TRACE-FAILED",
                passed_count=1,
                ignored_count=0,
                error_count=0,
                delivery_count=0,
                kingdee_tracking_id=None,
                task_name="daily-direct-order",
                created_at="2026-04-30T12:00:00",
                window_start="2026-04-30T08:00:00",
                window_end="2026-04-30T12:00:00",
                push_status=PushStatus.FAILED,
                kingdee_status=KingdeeStatus.PENDING,
                failure_stage="message_push",
                failure_reason="RuntimeError: message gateway down",
            )
        )

        self.assertEqual(payload["push_status"], "推送失败")
        self.assertEqual(payload["kingdee_status"], "采购申请单待提交")
        self.assertEqual(payload["failure_stage"], "message_push")
    # === MODIFIED END ===


def make_summary(trace_id: str, passed_count: int) -> RunSummary:
    """Builds a task run summary for persistence tests."""

    return RunSummary(
        trace_id=trace_id,
        passed_count=passed_count,
        ignored_count=0,
        error_count=0,
        delivery_count=passed_count,
        kingdee_tracking_id=f"KINGDEE-{trace_id}",
        # === MODIFIED START ===
        # 原因：任务历史测试需要覆盖新增状态和时间窗字段。
        # 影响范围：测试数据构造。
        task_name="daily-direct-order",
        created_at="2026-04-30T12:00:00",
        window_start="2026-04-30T08:00:00",
        window_end="2026-04-30T12:00:00",
        push_status=PushStatus.SUCCESS,
        kingdee_status=KingdeeStatus.SUCCESS,
        # === MODIFIED END ===
    )
