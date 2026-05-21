from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from re import sub
from typing import Any

from domain.enums.execution_log import ExecutionLogResult, ExecutionLogStage
from shared.logging.logger import sanitize_payload


EXECUTION_LOG_CSV_HEADERS = (
    "创建时间",
    "任务批次",
    "任务名称",
    "阶段",
    "结果",
    "说明",
    "影响",
    "建议",
)


@dataclass(frozen=True, slots=True)
class ExecutionLogRecord:
    """Business-readable execution log record attached to one task trace id."""

    created_at: str
    trace_id: str
    task_name: str
    stage: ExecutionLogStage
    result: ExecutionLogResult
    summary: str
    impact: str = ""
    suggestion: str = ""
    details: dict[str, object] = field(default_factory=dict)


class ExecutionLogStore:
    """Persists task execution logs and exports them for operation review."""

    def __init__(
        self,
        history_path: str | Path = Path("outputs") / "execution_logs.json",
        export_dir: str | Path = Path("outputs") / "execution_log_exports",
    ) -> None:
        self.history_path = Path(history_path)
        self.export_dir = Path(export_dir)

    def append(self, record: ExecutionLogRecord) -> None:
        """Appends one execution log record to local JSON history."""

        self.append_many((record,))

    def append_many(self, records: tuple[ExecutionLogRecord, ...] | list[ExecutionLogRecord]) -> None:
        """Appends execution log records to local JSON history."""

        if not records:
            return

        raw_records = self._load_records()
        raw_records.extend(execution_log_to_dict(record) for record in records)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(raw_records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_recent(
        self,
        limit: int | None = None,
        trace_id: str | None = None,
        stage: str | ExecutionLogStage | None = None,
        result: str | ExecutionLogResult | None = None,
        # === MODIFIED START ===
        # 原因：执行日志展示改为按周期筛选，避免固定条数截断同一批次的阶段日志。
        # 影响范围：执行日志查询。
        start_at: str | None = None,
        end_at: str | None = None,
        # === MODIFIED END ===
    ) -> tuple[ExecutionLogRecord, ...]:
        """Returns recent execution logs from newest to oldest."""

        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
            raise ValueError("limit must be a positive integer")

        normalized_trace_id = _optional_trace_id(trace_id)
        normalized_stage = _optional_stage(stage)
        normalized_result = _optional_result(result)
        # === MODIFIED START ===
        # 原因：执行日志支持按写入时间范围查询。
        # 影响范围：ExecutionLogStore.list_recent。
        start_epoch = _optional_datetime_epoch(start_at, "start_at")
        end_epoch = _optional_datetime_epoch(end_at, "end_at")
        if start_epoch is not None and end_epoch is not None and start_epoch > end_epoch:
            raise ValueError("start_at must be earlier than or equal to end_at")
        # === MODIFIED END ===
        records = [
            _record_from_dict(record)
            for record in self._load_records()
            if _matches(record, normalized_trace_id, normalized_stage, normalized_result, start_epoch, end_epoch)
        ]
        if limit is not None:
            records = records[-limit:]
        return tuple(reversed(records))

    def export_csv(
        self,
        trace_id: str | None = None,
        stage: str | ExecutionLogStage | None = None,
        result: str | ExecutionLogResult | None = None,
        # === MODIFIED START ===
        # 原因：执行日志下载需要和页面周期筛选保持一致。
        # 影响范围：ExecutionLogStore.export_csv。
        start_at: str | None = None,
        end_at: str | None = None,
        # === MODIFIED END ===
    ) -> Path:
        """Exports filtered execution logs to a CSV file."""

        normalized_trace_id = _optional_trace_id(trace_id)
        normalized_stage = _optional_stage(stage)
        normalized_result = _optional_result(result)
        # === MODIFIED START ===
        # 原因：下载执行日志支持按写入时间范围过滤。
        # 影响范围：ExecutionLogStore.export_csv。
        start_epoch = _optional_datetime_epoch(start_at, "start_at")
        end_epoch = _optional_datetime_epoch(end_at, "end_at")
        if start_epoch is not None and end_epoch is not None and start_epoch > end_epoch:
            raise ValueError("start_at must be earlier than or equal to end_at")
        # === MODIFIED END ===
        self.export_dir.mkdir(parents=True, exist_ok=True)
        name_parts = ["execution_logs"]
        if normalized_trace_id is not None:
            name_parts.append(_safe_name(normalized_trace_id))
        if normalized_stage is not None:
            name_parts.append(_safe_name(normalized_stage.value))
        if normalized_result is not None:
            name_parts.append(_safe_name(normalized_result.value))
        file_path = self.export_dir / f"{'_'.join(name_parts)}_{datetime.now():%Y%m%d%H%M%S}.csv"
        rows = [
            _csv_row(_record_from_dict(record))
            for record in self._load_records()
            if _matches(record, normalized_trace_id, normalized_stage, normalized_result, start_epoch, end_epoch)
        ]

        with file_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(EXECUTION_LOG_CSV_HEADERS)
            writer.writerows(rows)

        return file_path

    def _load_records(self) -> list[dict[str, object]]:
        """Loads raw execution log records from local JSON history."""

        if not self.history_path.exists():
            return []

        data = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("execution log history must be a list")

        records: list[dict[str, object]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("execution log history items must be objects")
            records.append(item)
        return records


def execution_log_to_dict(record: ExecutionLogRecord) -> dict[str, object]:
    """Converts an execution log record into JSON-compatible data."""

    return {
        "created_at": record.created_at,
        "trace_id": record.trace_id,
        "task_name": record.task_name,
        "stage": record.stage.value,
        "result": record.result.value,
        "summary": record.summary,
        "impact": record.impact,
        "suggestion": record.suggestion,
        "details": _safe_details(record.details),
    }


def execution_logs_to_payload(records: tuple[ExecutionLogRecord, ...]) -> dict[str, object]:
    """Converts execution logs into an API response payload."""

    return {
        "items": [execution_log_to_dict(record) for record in records],
    }


def _record_from_dict(data: dict[str, Any]) -> ExecutionLogRecord:
    return ExecutionLogRecord(
        created_at=_required_string(data, "created_at"),
        trace_id=_required_string(data, "trace_id"),
        task_name=_optional_string(data, "task_name"),
        stage=_stage(data.get("stage")),
        result=_result(data.get("result")),
        summary=_required_string(data, "summary"),
        impact=_optional_string(data, "impact"),
        suggestion=_optional_string(data, "suggestion"),
        details=_details(data.get("details")),
    )


def _csv_row(record: ExecutionLogRecord) -> list[object]:
    return [
        record.created_at,
        record.trace_id,
        record.task_name,
        record.stage.value,
        record.result.value,
        record.summary,
        record.impact,
        record.suggestion,
    ]


def _matches(
    data: dict[str, object],
    trace_id: str | None,
    stage: ExecutionLogStage | None,
    result: ExecutionLogResult | None,
    start_epoch: float | None = None,
    end_epoch: float | None = None,
) -> bool:
    if trace_id is not None and data.get("trace_id") != trace_id:
        return False
    if stage is not None and data.get("stage") != stage.value:
        return False
    if result is not None and data.get("result") != result.value:
        return False
    # === MODIFIED START ===
    # 原因：执行日志展示周期需要按日志写入时间过滤。
    # 影响范围：执行日志查询和下载。
    if start_epoch is not None or end_epoch is not None:
        created_epoch = _optional_datetime_epoch(data.get("created_at"), "created_at")
        if created_epoch is None:
            return False
        if start_epoch is not None and created_epoch < start_epoch:
            return False
        if end_epoch is not None and created_epoch > end_epoch:
            return False
    # === MODIFIED END ===
    return True


def _optional_trace_id(trace_id: str | None) -> str | None:
    if trace_id is None:
        return None
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("trace_id must be a non-empty string")
    return trace_id.strip()


def _optional_stage(value: str | ExecutionLogStage | None) -> ExecutionLogStage | None:
    if value is None:
        return None
    return _stage(value)


def _optional_result(value: str | ExecutionLogResult | None) -> ExecutionLogResult | None:
    if value is None:
        return None
    return _result(value)


# === MODIFIED START ===
# 原因：执行日志周期筛选需要解析 ISO 时间，并兼容前端 toISOString() 的 Z 后缀。
# 影响范围：执行日志查询和下载。
def _optional_datetime_epoch(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty ISO datetime string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO datetime string") from exc
# === MODIFIED END ===


def _stage(value: Any) -> ExecutionLogStage:
    if isinstance(value, ExecutionLogStage):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("stage must be a non-empty string")
    normalized = value.strip()
    for stage in ExecutionLogStage:
        if normalized in (stage.value, stage.name):
            return stage
    raise ValueError(f"Unsupported execution log stage: {value}")


def _result(value: Any) -> ExecutionLogResult:
    if isinstance(value, ExecutionLogResult):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("result must be a non-empty string")
    normalized = value.strip()
    for result in ExecutionLogResult:
        if normalized in (result.value, result.name):
            return result
    raise ValueError(f"Unsupported execution log result: {value}")


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


def _details(value: Any) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("details must be an object")
    return _safe_details(value)


def _safe_details(value: dict[str, object]) -> dict[str, object]:
    sanitized = sanitize_payload(value)
    return json.loads(json.dumps(sanitized, ensure_ascii=False, default=str))


def _safe_name(value: str) -> str:
    safe_value = sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe_value or "filter"
