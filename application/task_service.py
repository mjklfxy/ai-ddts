from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

# === MODIFIED START ===
# 原因：任务批次编码改为当天日期 + 四位数日内累计，由应用层生成。
# 影响范围：TaskService 默认 trace_id/task_id 生成逻辑。
from application.task_code import DailyTaskCodeGenerator
# === MODIFIED END ===
from domain.enums.status import KingdeeStatus, PaymentStatus, PushStatus


TraceIdGenerator = Callable[[], str]
Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Application task context shared across pipeline stages."""

    task_id: str
    trace_id: str
    task_name: str
    created_at: datetime
    window_start: datetime
    window_end: datetime
    push_status: PushStatus
    payment_status: PaymentStatus
    kingdee_status: KingdeeStatus


class TaskService:
    """Creates task contexts with task batch codes and initial statuses."""

    def __init__(
        self,
        trace_id_generator: TraceIdGenerator | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.clock = clock or datetime.now
        # === MODIFIED START ===
        # 原因：默认任务批次编码需符合 yyyyMMdd + 四位数累计格式。
        # 影响范围：未注入 trace_id_generator 的任务创建入口。
        self.trace_id_generator = trace_id_generator or DailyTaskCodeGenerator(clock=self.clock)
        # === MODIFIED END ===

    def create_task(
        self,
        task_name: str,
        window_start: datetime,
        window_end: datetime,
    ) -> TaskContext:
        trace_id = self.trace_id_generator()
        return TaskContext(
            task_id=trace_id,
            trace_id=trace_id,
            task_name=task_name,
            created_at=self.clock(),
            window_start=window_start,
            window_end=window_end,
            push_status=PushStatus.PENDING,
            payment_status=PaymentStatus.UNPAID,
            kingdee_status=KingdeeStatus.PENDING,
        )
