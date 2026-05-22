from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.config_service import ScheduleConfig
from application.manual_runner import RunSummary
from application.scheduler import DailyFixedTimeScheduler, SchedulerStateStore
from domain.enums.status import SchedulerStatus


class SchedulerTests(TestCase):
    """Tests fixed daily scheduler tick behavior."""

    def test_disabled_scheduler_does_not_run_task(self) -> None:
        runs: list[RunSummary] = []
        scheduler = make_scheduler(clock=lambda: datetime(2026, 4, 30, 10, 0, 0), runs=runs)

        result = scheduler.tick(ScheduleConfig(enabled=False, run_at="09:00"))

        self.assertEqual(result.status, SchedulerStatus.DISABLED)
        self.assertFalse(result.should_run)
        self.assertEqual(runs, [])

    def test_not_due_scheduler_does_not_run_task(self) -> None:
        runs: list[RunSummary] = []
        scheduler = make_scheduler(clock=lambda: datetime(2026, 4, 30, 8, 59, 0), runs=runs)

        result = scheduler.tick(ScheduleConfig(enabled=True, run_at="09:00"))

        self.assertEqual(result.status, SchedulerStatus.NOT_DUE)
        self.assertFalse(result.should_run)
        self.assertEqual(runs, [])

    def test_due_scheduler_runs_once_and_marks_state(self) -> None:
        runs: list[RunSummary] = []
        state_path = Path("tmp") / "test_scheduler" / "state_due.json"
        if state_path.exists():
            state_path.unlink()
        scheduler = make_scheduler(
            clock=lambda: datetime(2026, 4, 30, 9, 1, 0),
            runs=runs,
            state_path=state_path,
        )

        result = scheduler.tick(ScheduleConfig(enabled=True, run_at="09:00"))

        self.assertEqual(result.status, SchedulerStatus.RAN)
        self.assertTrue(result.should_run)
        self.assertEqual(result.summary.trace_id, "TRACE-SCHEDULED")
        self.assertEqual(
            [(schedule.schedule_id, summary.trace_id) for schedule, summary in runs],
            [("default", "TRACE-SCHEDULED")],
        )
        state = SchedulerStateStore(state_path).load()
        self.assertEqual(state.last_run_date, "2026-04-30")
        self.assertEqual(state.last_trace_id, "TRACE-SCHEDULED")

    def test_already_ran_today_does_not_run_again(self) -> None:
        runs: list[RunSummary] = []
        state_path = Path("tmp") / "test_scheduler" / "state_already.json"
        SchedulerStateStore(state_path).mark_run(
            run_date="2026-04-30",
            run_at="09:00",
            trace_id="TRACE-OLD",
        )
        scheduler = make_scheduler(
            clock=lambda: datetime(2026, 4, 30, 10, 0, 0),
            runs=runs,
            state_path=state_path,
        )

        result = scheduler.tick(ScheduleConfig(enabled=True, run_at="09:00"))

        self.assertEqual(result.status, SchedulerStatus.ALREADY_RAN)
        self.assertFalse(result.should_run)
        self.assertEqual(runs, [])

    def test_status_reports_due_without_running(self) -> None:
        runs: list[RunSummary] = []
        scheduler = make_scheduler(clock=lambda: datetime(2026, 4, 30, 10, 0, 0), runs=runs)

        payload = scheduler.status(ScheduleConfig(enabled=True, run_at="09:00"))

        self.assertTrue(payload["due"])
        self.assertEqual(runs, [])

    # === MODIFIED START ===
    # 原因：定时任务配置支持多条，需要返回每条配置的独立状态。
    # 影响范围：Scheduler status_many。
    def test_status_many_reports_multiple_schedule_items(self) -> None:
        runs: list[RunSummary] = []
        scheduler = make_scheduler(clock=lambda: datetime(2026, 4, 30, 10, 0, 0), runs=runs)

        payload = scheduler.status_many(
            (
                ScheduleConfig(
                    enabled=True,
                    run_at="09:00",
                    schedule_id="morning",
                    name="上午任务",
                ),
                ScheduleConfig(
                    enabled=False,
                    run_at="13:00",
                    schedule_id="afternoon",
                    name="下午任务",
                ),
            )
        )

        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["schedule_id"], "morning")
        self.assertEqual(payload["items"][0]["name"], "上午任务")
        self.assertEqual(payload["enabled_count"], 1)
        self.assertEqual(payload["due_count"], 1)
        self.assertEqual(runs, [])

    def test_tick_many_runs_each_due_schedule_once(self) -> None:
        runs: list[tuple[str, RunSummary]] = []
        state_path = Path("tmp") / "test_scheduler" / "state_many.json"
        if state_path.exists():
            state_path.unlink()
        scheduler = make_scheduler(
            clock=lambda: datetime(2026, 4, 30, 14, 0, 0),
            runs=runs,
            state_path=state_path,
        )

        payload = scheduler.tick_many(
            (
                ScheduleConfig(
                    enabled=True,
                    run_at="09:00",
                    schedule_id="morning",
                    name="上午任务",
                ),
                ScheduleConfig(
                    enabled=True,
                    run_at="13:00",
                    schedule_id="afternoon",
                    name="下午任务",
                ),
            )
        )

        self.assertTrue(payload["should_run"])
        self.assertEqual(payload["ran_count"], 2)
        self.assertEqual(
            [(schedule.schedule_id, summary.trace_id) for schedule, summary in runs],
            [("morning", "TRACE-SCHEDULED"), ("afternoon", "TRACE-SCHEDULED")],
        )
        state = SchedulerStateStore(state_path).load()
        self.assertEqual(sorted(state.schedule_runs), ["afternoon", "morning"])

    def test_legacy_run_state_only_blocks_default_schedule(self) -> None:
        runs: list[RunSummary] = []
        state_path = Path("tmp") / "test_scheduler" / "state_legacy_default.json"
        if state_path.exists():
            state_path.unlink()
        SchedulerStateStore(state_path).mark_run(
            run_date="2026-04-30",
            run_at="09:00",
            trace_id="TRACE-OLD",
        )
        scheduler = make_scheduler(
            clock=lambda: datetime(2026, 4, 30, 10, 0, 0),
            runs=runs,
            state_path=state_path,
        )

        default_result = scheduler.tick(ScheduleConfig(enabled=True, run_at="09:00"))
        other_result = scheduler.tick(
            ScheduleConfig(
                enabled=True,
                run_at="09:00",
                schedule_id="extra",
                name="新增任务",
            )
        )

        self.assertEqual(default_result.status, SchedulerStatus.ALREADY_RAN)
        self.assertEqual(other_result.status, SchedulerStatus.RAN)
        self.assertEqual(
            [(schedule.schedule_id, summary.trace_id) for schedule, summary in runs],
            [("extra", "TRACE-SCHEDULED")],
        )
    # === MODIFIED END ===


def make_scheduler(
    clock,
    runs: list,
    state_path: Path | None = None,
) -> DailyFixedTimeScheduler:
    """Builds a deterministic scheduler for tests."""

    path = state_path or Path("tmp") / "test_scheduler" / "state.json"
    if state_path is None and path.exists():
        path.unlink()
    return DailyFixedTimeScheduler(
        state_store=SchedulerStateStore(path),
        task_runner=lambda schedule: make_summary(),
        task_recorder=lambda schedule, summary: runs.append((schedule, summary)),
        clock=clock,
    )


def make_summary() -> RunSummary:
    """Builds a scheduled task summary for tests."""

    return RunSummary(
        trace_id="TRACE-SCHEDULED",
        passed_count=1,
        ignored_count=0,
        error_count=0,
        delivery_count=1,
        kingdee_tracking_id="KINGDEE-SCHEDULED",
    )
