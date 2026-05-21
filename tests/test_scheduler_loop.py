import asyncio
from unittest import TestCase

from application.scheduler_loop import BackgroundSchedulerLoop


class BackgroundSchedulerLoopTests(TestCase):
    """Tests background scheduler loop lifecycle and tick logging."""

    def test_tick_once_runs_callback_and_logs_result(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        loop = BackgroundSchedulerLoop(
            tick_callback=lambda: {"status": "未启用", "should_run": False},
            interval_seconds_provider=lambda: 60,
            log_info=lambda event, payload: logs.append((event, payload)),
        )

        result = loop.tick_once()

        self.assertEqual(result["status"], "未启用")
        self.assertEqual(logs[0][0], "scheduler_loop_tick")
        self.assertEqual(logs[0][1]["trace_id"], "scheduler")

    def test_status_reports_interval_and_running_state(self) -> None:
        loop = BackgroundSchedulerLoop(
            tick_callback=lambda: {"status": "未启用", "should_run": False},
            interval_seconds_provider=lambda: 30,
        )

        self.assertEqual(
            loop.status(),
            {
                "running": False,
                "interval_seconds": 30,
            },
        )

    def test_start_and_stop_manage_background_task(self) -> None:
        async def scenario() -> None:
            ticks: list[int] = []
            loop = BackgroundSchedulerLoop(
                tick_callback=lambda: ticks.append(1) or {"status": "未启用", "should_run": False},
                interval_seconds_provider=lambda: 60,
            )

            await loop.start()
            await asyncio.sleep(0)
            self.assertTrue(loop.is_running)
            self.assertEqual(len(ticks), 1)

            await loop.stop()
            self.assertFalse(loop.is_running)

        asyncio.run(scenario())

    def test_invalid_interval_is_rejected(self) -> None:
        loop = BackgroundSchedulerLoop(
            tick_callback=lambda: {"status": "未启用", "should_run": False},
            interval_seconds_provider=lambda: 0,
        )

        with self.assertRaisesRegex(ValueError, "interval"):
            loop.status()
