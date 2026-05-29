from __future__ import annotations

import asyncio
from collections.abc import Callable


class SchedulerLoopLogInfo:
    """Callable protocol-like base for scheduler loop info logs."""

    def __call__(self, event: str, payload: dict[str, object]) -> None:
        """Records one scheduler loop info event."""


class SchedulerLoopLogError:
    """Callable protocol-like base for scheduler loop error logs."""

    def __call__(self, event: str, payload: dict[str, object]) -> None:
        """Records one scheduler loop error event."""


class BackgroundSchedulerLoop:
    """Runs scheduler ticks in a background asyncio loop."""

    def __init__(
        self,
        tick_callback: Callable[[], dict[str, object]],
        interval_seconds_provider: Callable[[], int],
        log_info: SchedulerLoopLogInfo | None = None,
        log_error: SchedulerLoopLogError | None = None,
    ) -> None:
        self.tick_callback = tick_callback
        self.interval_seconds_provider = interval_seconds_provider
        self.log_info = log_info or self._noop_log
        self.log_error = log_error or self._noop_log
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Returns whether the background scheduler loop task is active."""

        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Starts the background scheduler loop if it is not already running."""

        if self.is_running:
            return
        self._task = asyncio.create_task(self._run_loop())
        self.log_info(
            "scheduler_loop_started",
            {
                "trace_id": "scheduler",
                "interval_seconds": self._safe_interval_seconds(),
            },
        )

    async def stop(self) -> None:
        """Stops the background scheduler loop if it is running."""

        if self._task is None:
            return

        task = self._task
        self._task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self.log_info("scheduler_loop_stopped", {"trace_id": "scheduler"})

    def tick_once(self) -> dict[str, object]:
        """Runs one scheduler tick and records a loop-level log."""

        result = self.tick_callback()
        self.log_info(
            "scheduler_loop_tick",
            {
                "trace_id": "scheduler",
                "status": result.get("status"),
                "should_run": result.get("should_run"),
            },
        )
        return result

    def status(self) -> dict[str, object]:
        """Returns background scheduler loop status."""

        return {
            "running": self.is_running,
            "interval_seconds": self._safe_interval_seconds(),
        }

    async def _run_loop(self) -> None:
        """Runs scheduler ticks until cancelled."""

        while True:
            try:
                self.tick_once()
            except Exception as exc:
                self.log_error(
                    "scheduler_loop_tick_failed",
                    {
                        "trace_id": "scheduler",
                        "error_type": exc.__class__.__name__,
                        "error": str(exc)[:200],
                    },
                )
            await asyncio.sleep(self._safe_interval_seconds())

    def _safe_interval_seconds(self) -> int:
        interval_seconds = self.interval_seconds_provider()
        if not isinstance(interval_seconds, int) or isinstance(interval_seconds, bool) or interval_seconds < 1:
            raise ValueError("scheduler loop interval must be a positive integer")
        return interval_seconds

    @staticmethod
    def _noop_log(event: str, payload: dict[str, object]) -> None:
        _ = (event, payload)
