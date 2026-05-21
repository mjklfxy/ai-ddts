import json
from pathlib import Path
from unittest import TestCase

from application.execution_log_store import (
    ExecutionLogRecord,
    ExecutionLogStore,
    execution_logs_to_payload,
)
from domain.enums.execution_log import ExecutionLogResult, ExecutionLogStage


class ExecutionLogStoreTests(TestCase):
    """Tests visual execution log persistence and export."""

    def setUp(self) -> None:
        self.history_path = Path("tmp") / "test_execution_log_store" / "execution_logs.json"
        self.export_dir = Path("tmp") / "test_execution_log_store" / "exports"
        if self.history_path.exists():
            self.history_path.unlink()
        self.store = ExecutionLogStore(
            history_path=self.history_path,
            export_dir=self.export_dir,
        )

    def test_missing_history_returns_empty_payload(self) -> None:
        records = self.store.list_recent()

        self.assertEqual(records, ())
        self.assertEqual(execution_logs_to_payload(records), {"items": []})

    def test_append_list_recent_and_filters(self) -> None:
        self.store.append(
            sample_log(
                trace_id="TRACE-001",
                stage=ExecutionLogStage.FETCH,
                result=ExecutionLogResult.SUCCESS,
                summary="已完成订单抓取",
            )
        )
        self.store.append(
            sample_log(
                trace_id="TRACE-002",
                stage=ExecutionLogStage.MESSAGE,
                result=ExecutionLogResult.FAILED,
                summary="沟通群推送失败",
            )
        )

        recent = self.store.list_recent(limit=2)
        self.assertEqual([item.trace_id for item in recent], ["TRACE-002", "TRACE-001"])

        filtered = self.store.list_recent(trace_id="TRACE-002", stage="推送群", result="失败")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].summary, "沟通群推送失败")

    # === MODIFIED START ===
    # 原因：执行日志展示从固定条数改为周期筛选，需要覆盖时间范围查询。
    # 影响范围：ExecutionLogStore.list_recent。
    def test_list_recent_can_filter_by_created_time_range(self) -> None:
        self.store.append(sample_log(trace_id="TRACE-OLD", created_at="2026-04-29T10:00:00"))
        self.store.append(sample_log(trace_id="TRACE-NEW", created_at="2026-04-30T12:00:00"))

        records = self.store.list_recent(
            start_at="2026-04-30T00:00:00",
            end_at="2026-04-30T23:59:59",
        )

        self.assertEqual([item.trace_id for item in records], ["TRACE-NEW"])
    # === MODIFIED END ===

    def test_export_csv_writes_readable_headers_and_rows(self) -> None:
        self.store.append(
            sample_log(
                trace_id="TRACE-001",
                stage=ExecutionLogStage.RULE,
                result=ExecutionLogResult.PARTIAL,
                summary="规则判断完成",
                impact="规则异常 1 单",
                suggestion="下载异常订单明细",
            )
        )

        file_path = self.store.export_csv(trace_id="TRACE-001")

        content = file_path.read_text(encoding="utf-8-sig")
        self.assertIn("创建时间,任务批次,任务名称,阶段,结果,说明,影响,建议", content)
        self.assertIn("TRACE-001", content)
        self.assertIn("部分成功", content)

    def test_rejects_invalid_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit"):
            self.store.list_recent(limit=0)

    def test_sensitive_details_are_redacted(self) -> None:
        self.store.append(
            sample_log(
                details={
                    "APP_SECRET": "secret-value",
                    "safe": "visible",
                }
            )
        )

        persisted = json.loads(self.history_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted[0]["details"]["APP_SECRET"], "[REDACTED]")
        self.assertEqual(persisted[0]["details"]["safe"], "visible")


def sample_log(
    created_at: str = "2026-04-30T12:00:00",
    trace_id: str = "TRACE-001",
    stage: ExecutionLogStage = ExecutionLogStage.TASK,
    result: ExecutionLogResult = ExecutionLogResult.SUCCESS,
    summary: str = "任务开始执行",
    impact: str = "",
    suggestion: str = "",
    details: dict[str, object] | None = None,
) -> ExecutionLogRecord:
    """Builds a deterministic execution log record for tests."""

    return ExecutionLogRecord(
        created_at=created_at,
        trace_id=trace_id,
        task_name="daily-direct-order",
        stage=stage,
        result=result,
        summary=summary,
        impact=impact,
        suggestion=suggestion,
        details=details or {},
    )
