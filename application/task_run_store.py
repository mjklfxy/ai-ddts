from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from application.manual_runner import RunSummary
from domain.enums.status import KingdeeStatus, PushStatus


class TaskRunStore:
    """Persists task run summaries for API queries."""

    def __init__(self, history_path: str | Path = Path("outputs") / "task_runs.json") -> None:
        self.history_path = Path(history_path)

    def append(self, summary: RunSummary) -> None:
        """Appends one task run summary to local JSON history."""

        records = self._load_records()
        # === MODIFIED START ===
        # 原因：RunSummary 包含 Enum，落盘时必须转为稳定中文状态值。
        # 影响范围：任务历史 JSON 结构。
        records.append(run_summary_to_dict(summary))
        # === MODIFIED END ===
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def latest(self) -> RunSummary | None:
        """Returns the latest persisted task run summary."""

        records = self._load_records()
        if not records:
            return None
        return _summary_from_dict(records[-1])

    def list_recent(self, limit: int = 20) -> tuple[RunSummary, ...]:
        """Returns recent task run summaries from newest to oldest."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")

        records = self._load_records()
        recent_records = records[-limit:]
        return tuple(_summary_from_dict(record) for record in reversed(recent_records))

    # === MODIFIED START ===
    # 原因：任务批次编码需要读取已持久化的历史批次号来做当天累计。
    # 影响范围：ApiService 运行任务和 Scheduler 运行任务的批次号生成。
    def list_trace_ids(self) -> tuple[str, ...]:
        """Returns persisted task trace ids in storage order."""

        trace_ids: list[str] = []
        for record in self._load_records():
            value = record.get("trace_id")
            if isinstance(value, str) and value.strip():
                trace_ids.append(value.strip())
        return tuple(trace_ids)
    # === MODIFIED END ===

    def _load_records(self) -> list[dict[str, object]]:
        """Loads raw task run records from local JSON history."""

        if not self.history_path.exists():
            return []

        data = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("task run history must be a list")

        records: list[dict[str, object]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("task run history items must be objects")
            records.append(item)
        return records


def _summary_from_dict(data: dict[str, Any]) -> RunSummary:
    """Converts persisted JSON data into a RunSummary."""

    kingdee_tracking_id = data.get("kingdee_tracking_id")
    if kingdee_tracking_id is not None and not isinstance(kingdee_tracking_id, str):
        raise ValueError("kingdee_tracking_id must be a string or null")

    return RunSummary(
        trace_id=_required_string(data, "trace_id"),
        passed_count=_non_negative_int(data, "passed_count"),
        ignored_count=_non_negative_int(data, "ignored_count"),
        error_count=_non_negative_int(data, "error_count"),
        delivery_count=_non_negative_int(data, "delivery_count"),
        kingdee_tracking_id=kingdee_tracking_id,
        # === MODIFIED START ===
        # 原因：兼容旧历史记录缺失状态字段，同时解析新状态字段为 Enum。
        # 影响范围：任务历史读取。
        task_name=_optional_string(data, "task_name"),
        created_at=_optional_string(data, "created_at"),
        window_start=_optional_string(data, "window_start"),
        window_end=_optional_string(data, "window_end"),
        push_status=_push_status(data.get("push_status")),
        kingdee_status=_kingdee_status(data.get("kingdee_status")),
        failure_stage=_optional_string(data, "failure_stage"),
        failure_reason=_optional_string(data, "failure_reason"),
        # === MODIFIED END ===
    )


# === MODIFIED START ===
# 原因：任务摘要响应和持久化都需要稳定 JSON 结构。
# 影响范围：TaskRunStore 与 ApiService。
def run_summary_to_dict(summary: RunSummary) -> dict[str, object]:
    """Converts a RunSummary into JSON-compatible data."""

    return {
        "trace_id": summary.trace_id,
        "passed_count": summary.passed_count,
        "ignored_count": summary.ignored_count,
        "error_count": summary.error_count,
        "delivery_count": summary.delivery_count,
        "kingdee_tracking_id": summary.kingdee_tracking_id,
        "task_name": summary.task_name,
        "created_at": summary.created_at,
        "window_start": summary.window_start,
        "window_end": summary.window_end,
        "push_status": summary.push_status.value,
        "kingdee_status": summary.kingdee_status.value,
        "failure_stage": summary.failure_stage,
        "failure_reason": summary.failure_reason,
    }
# === MODIFIED END ===


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value.strip() or None


def _non_negative_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


# === MODIFIED START ===
# 原因：所有状态字段必须使用 Enum，历史 JSON 读取时需要做值映射。
# 影响范围：任务历史反序列化。
def _push_status(value: Any) -> PushStatus:
    if value is None:
        return PushStatus.PENDING
    for status in PushStatus:
        if value == status.value:
            return status
    raise ValueError(f"Unsupported push_status: {value}")


def _kingdee_status(value: Any) -> KingdeeStatus:
    if value is None:
        return KingdeeStatus.PENDING
    for status in KingdeeStatus:
        if value == status.value:
            return status
    raise ValueError(f"Unsupported kingdee_status: {value}")
# === MODIFIED END ===
