from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from application.config_service import ScheduleConfig
from application.manual_runner import RunSummary
from domain.enums.status import SchedulerStatus


@dataclass(frozen=True, slots=True)
class SchedulerRunState:
    """Persisted run state for one schedule configuration."""

    last_run_date: str | None = None
    last_run_at: str | None = None
    last_trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class SchedulerState:
    """Persisted state used to prevent duplicate daily scheduled runs."""

    last_run_date: str | None = None
    last_run_at: str | None = None
    last_trace_id: str | None = None
    # === MODIFIED START ===
    # 原因：支持多条定时任务配置，每条配置需要独立记录当天是否已运行。
    # 影响范围：SchedulerStateStore、DailyFixedTimeScheduler。
    schedule_runs: dict[str, SchedulerRunState] = field(default_factory=dict)
    # === MODIFIED END ===

    def run_for(self, schedule_id: str) -> SchedulerRunState:
        """Returns persisted run state for one schedule id."""

        # === MODIFIED START ===
        # 原因：多条定时任务配置中，只有旧版 default 配置应继承历史单条状态。
        # 影响范围：新增 schedule_id 的首次到点判断。
        if schedule_id in self.schedule_runs:
            return self.schedule_runs[schedule_id]
        if schedule_id == "default":
            return SchedulerRunState(
                last_run_date=self.last_run_date,
                last_run_at=self.last_run_at,
                last_trace_id=self.last_trace_id,
            )
        return SchedulerRunState()
        # === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    """Result of one scheduler tick evaluation."""

    status: SchedulerStatus
    reason: str
    should_run: bool
    now: str
    run_at: str
    last_run_date: str | None
    summary: RunSummary | None = None
    # === MODIFIED START ===
    # 原因：多条定时任务配置需要在状态和 tick 结果中标识具体配置。
    # 影响范围：Scheduler API 响应。
    schedule_id: str = "default"
    schedule_name: str = "默认定时任务"
    # === MODIFIED END ===


class SchedulerStateStore:
    """Persists scheduler state for fixed daily runs."""

    def __init__(self, state_path: str | Path = Path("outputs") / "scheduler_state.json") -> None:
        self.state_path = Path(state_path)

    def load(self) -> SchedulerState:
        """Loads the scheduler state from local JSON storage."""

        if not self.state_path.exists():
            return SchedulerState()

        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("scheduler state must be an object")

        # === MODIFIED START ===
        # 原因：多条定时任务配置需要从 schedule_runs 读取独立运行状态，并兼容旧状态文件。
        # 影响范围：Scheduler 状态读取。
        schedule_runs = _schedule_runs(data.get("schedule_runs"))
        # === MODIFIED END ===
        return SchedulerState(
            last_run_date=_optional_string(data, "last_run_date"),
            last_run_at=_optional_string(data, "last_run_at"),
            last_trace_id=_optional_string(data, "last_trace_id"),
            # === MODIFIED START ===
            # 原因：携带多条定时任务的运行状态。
            # 影响范围：SchedulerStateStore.load。
            schedule_runs=schedule_runs,
            # === MODIFIED END ===
        )

    def mark_run(
        self,
        run_date: str,
        run_at: str,
        trace_id: str,
        schedule_id: str = "default",
    ) -> None:
        """Persists the latest successful scheduled run state."""

        schedule_key = _required_string(schedule_id, "schedule_id")
        state = self.load()
        schedule_runs = {
            key: {
                "last_run_date": run_state.last_run_date,
                "last_run_at": run_state.last_run_at,
                "last_trace_id": run_state.last_trace_id,
            }
            for key, run_state in state.schedule_runs.items()
        }
        schedule_runs[schedule_key] = {
            "last_run_date": _required_string(run_date, "last_run_date"),
            "last_run_at": _required_string(run_at, "last_run_at"),
            "last_trace_id": _required_string(trace_id, "last_trace_id"),
        }
        state = {
            "last_run_date": _required_string(run_date, "last_run_date"),
            "last_run_at": _required_string(run_at, "last_run_at"),
            "last_trace_id": _required_string(trace_id, "last_trace_id"),
            # === MODIFIED START ===
            # 原因：多条定时任务配置各自保留最近运行状态。
            # 影响范围：Scheduler 状态落盘结构。
            "schedule_runs": schedule_runs,
            # === MODIFIED END ===
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # === MODIFIED START ===
    # 原因：定时任务失败后需要强行修改上次运行时间，允许重新触发。
    # 影响范围：/scheduler/state PUT。
    def update_schedule_state(
        self,
        schedule_id: str,
        *,
        last_run_date: str | None = None,
        last_run_at: str | None = None,
        last_trace_id: str | None = None,
    ) -> None:
        """Force-updates the persisted state for one schedule."""

        schedule_key = _required_string(schedule_id, "schedule_id")
        state = self.load()
        existing = state.schedule_runs.get(schedule_key, SchedulerRunState())

        schedule_runs = {
            key: {
                "last_run_date": run_state.last_run_date,
                "last_run_at": run_state.last_run_at,
                "last_trace_id": run_state.last_trace_id,
            }
            for key, run_state in state.schedule_runs.items()
        }
        schedule_runs[schedule_key] = {
            "last_run_date": last_run_date if last_run_date is not None else existing.last_run_date,
            "last_run_at": last_run_at if last_run_at is not None else existing.last_run_at,
            "last_trace_id": last_trace_id if last_trace_id is not None else existing.last_trace_id,
        }
        latest = schedule_runs[schedule_key]
        state = {
            "last_run_date": latest["last_run_date"],
            "last_run_at": latest["last_run_at"],
            "last_trace_id": latest["last_trace_id"],
            "schedule_runs": schedule_runs,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    # === MODIFIED END ===


class DailyFixedTimeScheduler:
    """Evaluates one fixed daily run time and triggers the task when due."""

    def __init__(
        self,
        state_store: SchedulerStateStore,
        task_runner: Callable[[ScheduleConfig], RunSummary],
        task_recorder: Callable[[ScheduleConfig, RunSummary], None],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_store = state_store
        self.task_runner = task_runner
        self.task_recorder = task_recorder
        self.clock = clock or datetime.now

    def status(self, schedule_config: ScheduleConfig) -> dict[str, object]:
        """Returns current scheduler status without running a task."""

        now = self.clock()
        state = self.state_store.load()
        # === MODIFIED START ===
        # 原因：多条定时任务配置需要按 schedule_id 读取独立运行状态。
        # 影响范围：单条 Scheduler 状态查询。
        run_state = state.run_for(schedule_config.schedule_id)
        # === MODIFIED END ===
        return {
            "schedule_id": schedule_config.schedule_id,
            "name": schedule_config.name,
            "enabled": schedule_config.enabled,
            "run_at": schedule_config.run_at,
            "now": now.isoformat(),
            "last_run_date": run_state.last_run_date,
            "last_run_at": run_state.last_run_at,
            "last_trace_id": run_state.last_trace_id,
            "due": _is_due(now, schedule_config, run_state),
        }

    # === MODIFIED START ===
    # 原因：调度器需要一次返回多条定时任务配置的运行状态。
    # 影响范围：/scheduler/status。
    def status_many(self, schedule_configs: tuple[ScheduleConfig, ...]) -> dict[str, object]:
        """Returns scheduler status for multiple schedule configurations."""

        items = [self.status(schedule_config) for schedule_config in schedule_configs]
        first = items[0] if items else {
            "schedule_id": "default",
            "name": "默认定时任务",
            "enabled": False,
            "run_at": "09:00",
            "now": self.clock().isoformat(),
            "last_run_date": None,
            "last_run_at": None,
            "last_trace_id": None,
            "due": False,
        }
        return {
            **first,
            "items": items,
            "enabled_count": sum(1 for item in items if item["enabled"]),
            "due_count": sum(1 for item in items if item["due"]),
        }
    # === MODIFIED END ===

    def tick(self, schedule_config: ScheduleConfig) -> SchedulerTickResult:
        """Evaluates schedule and runs the task once when due."""

        now = self.clock()
        state = self.state_store.load()
        # === MODIFIED START ===
        # 原因：多条定时任务配置需要独立判断当天是否已运行。
        # 影响范围：Scheduler tick。
        run_state = state.run_for(schedule_config.schedule_id)
        # === MODIFIED END ===

        if not schedule_config.enabled:
            return SchedulerTickResult(
                status=SchedulerStatus.DISABLED,
                reason="scheduler_disabled",
                should_run=False,
                now=now.isoformat(),
                run_at=schedule_config.run_at,
                last_run_date=run_state.last_run_date,
                schedule_id=schedule_config.schedule_id,
                schedule_name=schedule_config.name,
            )

        if run_state.last_run_date == now.date().isoformat():
            return SchedulerTickResult(
                status=SchedulerStatus.ALREADY_RAN,
                reason="already_ran_today",
                should_run=False,
                now=now.isoformat(),
                run_at=schedule_config.run_at,
                last_run_date=run_state.last_run_date,
                schedule_id=schedule_config.schedule_id,
                schedule_name=schedule_config.name,
            )

        if now.strftime("%H:%M") < schedule_config.run_at:
            return SchedulerTickResult(
                status=SchedulerStatus.NOT_DUE,
                reason="not_due",
                should_run=False,
                now=now.isoformat(),
                run_at=schedule_config.run_at,
                last_run_date=run_state.last_run_date,
                schedule_id=schedule_config.schedule_id,
                schedule_name=schedule_config.name,
            )

        summary = self.task_runner(schedule_config)
        self.task_recorder(schedule_config, summary)
        self.state_store.mark_run(
            run_date=now.date().isoformat(),
            run_at=schedule_config.run_at,
            trace_id=summary.trace_id,
            schedule_id=schedule_config.schedule_id,
        )
        return SchedulerTickResult(
            status=SchedulerStatus.RAN,
            reason="scheduled_task_ran",
            should_run=True,
            now=now.isoformat(),
            run_at=schedule_config.run_at,
            last_run_date=run_state.last_run_date,
            summary=summary,
            schedule_id=schedule_config.schedule_id,
            schedule_name=schedule_config.name,
        )

    def tick_many(self, schedule_configs: tuple[ScheduleConfig, ...]) -> dict[str, object]:
        """Evaluates multiple schedule configurations and runs all due items."""

        results = [self.tick(schedule_config) for schedule_config in schedule_configs]
        items = [scheduler_tick_to_dict(result) for result in results]
        ran_results = [result for result in results if result.should_run]
        first = items[0] if items else {
            "status": SchedulerStatus.DISABLED.value,
            "reason": "no_schedules",
            "should_run": False,
            "now": self.clock().isoformat(),
            "run_at": "09:00",
            "last_run_date": None,
            "schedule_id": "default",
            "name": "默认定时任务",
        }
        return {
            **first,
            "should_run": bool(ran_results),
            "ran_count": len(ran_results),
            "items": items,
            "summaries": [result.summary for result in ran_results if result.summary is not None],
        }
    # === MODIFIED END ===


def scheduler_tick_to_dict(result: SchedulerTickResult) -> dict[str, object]:
    """Converts scheduler tick result into API-safe data."""

    return {
        "schedule_id": result.schedule_id,
        "name": result.schedule_name,
        "status": result.status.value,
        "reason": result.reason,
        "should_run": result.should_run,
        "now": result.now,
        "run_at": result.run_at,
        "last_run_date": result.last_run_date,
    }


def _is_due(now: datetime, schedule_config: ScheduleConfig, state: SchedulerRunState) -> bool:
    if not schedule_config.enabled:
        return False
    if state.last_run_date == now.date().isoformat():
        return False
    return now.strftime("%H:%M") >= schedule_config.run_at


# === MODIFIED START ===
# 原因：Scheduler 状态文件需要解析多条 schedule_id 对应的运行状态。
# 影响范围：SchedulerStateStore.load。
def _schedule_runs(value: Any) -> dict[str, SchedulerRunState]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("schedule_runs must be an object")

    result: dict[str, SchedulerRunState] = {}
    for schedule_id, run_state in value.items():
        if not isinstance(schedule_id, str) or not schedule_id.strip():
            raise ValueError("schedule_runs keys must be non-empty strings")
        if not isinstance(run_state, dict):
            raise ValueError("schedule_runs values must be objects")
        result[schedule_id.strip()] = SchedulerRunState(
            last_run_date=_optional_string(run_state, "last_run_date"),
            last_run_at=_optional_string(run_state, "last_run_at"),
            last_trace_id=_optional_string(run_state, "last_trace_id"),
        )
    return result
# === MODIFIED END ===


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when provided")
    return value.strip()


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
