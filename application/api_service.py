from __future__ import annotations

import json
from pathlib import Path

# === MODIFIED START ===
# 原因：复用配置服务的统一序列化，避免 API 返回结构和落盘结构分叉。
# 影响范围：接口配置读取与更新返回。
from application.config_service import AppConfig, ConfigService, to_dict
# === MODIFIED END ===
from domain.rules.region_rule import RestrictedRegion
# === MODIFIED START ===
# 原因：API 需要提供可视化执行日志查询和下载能力。
# 影响范围：执行日志接口服务。
from application.execution_log_store import ExecutionLogStore, execution_logs_to_payload
# === MODIFIED END ===
# === MODIFIED START ===
# 原因：异常订单需要从 API 查询和下载。
# 影响范围：异常订单接口服务。
from application.exception_order_store import ExceptionOrderStore, exception_orders_to_payload
# === MODIFIED END ===
# === MODIFIED START ===
# 原因：任务付款状态由上传回执判断，需要 API 服务读写付款回执存储。
# 影响范围：付款状态与回执上传接口。
from application.payment_receipt_store import PaymentReceiptStore, payment_receipt_to_dict
# === MODIFIED END ===
# === MODIFIED START ===
# 原因：任务清单需要按批次下载正常推送订单明细。
# 影响范围：任务下载接口服务。
from application.pushed_order_store import PushedOrderStore
# === MODIFIED END ===
# === MODIFIED START ===
# 原因：提供固定时间 Scheduler 的状态查询和 tick 触发能力。
# 影响范围：调度器接口服务。
from application.scheduler import (
    DailyFixedTimeScheduler,
    SchedulerStateStore,
    scheduler_tick_to_dict,
)
from application.scheduler_loop import BackgroundSchedulerLoop
# === MODIFIED END ===
# === MODIFIED START ===
# 原因：任务接口需要运行任务并持久化任务摘要。
# 影响范围：任务运行和任务查询接口。
from application.manual_runner import run_once
from application.supplier_mapping_store import (
    SupplierMappingStore,
    suppliers_to_payload,
)
from application.task_run_store import TaskRunStore, run_summary_to_dict
# === MODIFIED END ===
from infrastructure.cloud_warehouse_client import CloudWarehouseClient
from infrastructure.xlsx_region_parser import load_restricted_regions_from_bytes
from infrastructure.xlsx_sku_group_parser import load_sku_groups_from_bytes
from infrastructure.xlsx_sku_parser import load_skus_from_bytes
from domain.sku_group_info import SkuGroupInfo
from shared.logging.logger import log_error, log_info


class ApiService:
    """Application service used by HTTP interfaces."""

    # === MODIFIED START ===
    # 原因：任务运行摘要需要持久化，不能只保存在服务内存里。
    # 影响范围：任务运行和查询接口。
    def __init__(
        self,
        config_path: str | Path = Path("config") / "config.json",
        task_store_path: str | Path = Path("outputs") / "task_runs.json",
        # === MODIFIED START ===
        # 原因：API 需要维护 ERP 同步来的 SKU-供应商对照数据。
        # 影响范围：供应商映射查询、导入和任务运行。
        supplier_mapping_path: str | Path = Path("outputs") / "sku_supplier_mappings.json",
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务运行产生的异常订单需要持久化和导出。
        # 影响范围：异常订单查询和下载接口。
        exception_order_path: str | Path = Path("outputs") / "exception_orders.json",
        exception_export_dir: str | Path = Path("outputs") / "exception_order_exports",
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务运行产生的正常推送订单明细需要持久化和导出。
        # 影响范围：任务清单正常订单下载接口。
        pushed_order_path: str | Path = Path("outputs") / "pushed_orders.json",
        pushed_order_export_dir: str | Path = Path("outputs") / "pushed_order_exports",
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：付款回执需要持久化，并按 trace_id 判断已付款/未付款。
        # 影响范围：任务付款状态接口。
        payment_receipt_path: str | Path = Path("outputs") / "payment_receipts.json",
        payment_receipt_dir: str | Path = Path("outputs") / "payment_receipts",
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：Scheduler 需要持久化每日是否已经运行过。
        # 影响范围：调度器状态和 tick 接口。
        scheduler_state_path: str | Path = Path("outputs") / "scheduler_state.json",
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：执行日志需要独立持久化和导出目录。
        # 影响范围：执行日志查询、下载和任务运行。
        execution_log_path: str | Path = Path("outputs") / "execution_logs.json",
        execution_log_export_dir: str | Path = Path("outputs") / "execution_log_exports",
        # === MODIFIED END ===
    ) -> None:
        self.config_path = Path(config_path)
        self.task_run_store = TaskRunStore(task_store_path)
        # === MODIFIED START ===
        # 原因：任务运行和供应商映射接口共用同一个本地映射存储。
        # 影响范围：/supplier-mappings 与 /tasks/mock-run。
        self.supplier_mapping_path = Path(supplier_mapping_path)
        self.supplier_mapping_store = SupplierMappingStore(self.supplier_mapping_path)
        self.supplier_client = CloudWarehouseClient(local_path=self.supplier_mapping_path)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：API 需要复用同一个异常订单存储。
        # 影响范围：/exception-orders 和 /exception-orders/download。
        self.exception_order_path = Path(exception_order_path)
        self.exception_order_store = ExceptionOrderStore(
            history_path=self.exception_order_path,
            export_dir=exception_export_dir,
        )
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：API 需要复用同一个正常推送订单明细存储。
        # 影响范围：/tasks/{trace_id}/pushed-orders/download。
        self.pushed_order_path = Path(pushed_order_path)
        self.pushed_order_store = PushedOrderStore(
            history_path=self.pushed_order_path,
            export_dir=pushed_order_export_dir,
        )
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：API 需要维护任务付款回执和付款状态。
        # 影响范围：/tasks/{trace_id}/payment 和 /tasks/{trace_id}/payment-receipt。
        self.payment_receipt_store = PaymentReceiptStore(
            history_path=payment_receipt_path,
            receipt_dir=payment_receipt_dir,
        )
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：API 需要复用固定时间调度器状态。
        # 影响范围：/scheduler/status 和 /scheduler/tick。
        self.scheduler_state_store = SchedulerStateStore(scheduler_state_path)
        self.scheduler_loop = BackgroundSchedulerLoop(
            tick_callback=self.tick_scheduler,
            interval_seconds_provider=self._scheduler_loop_interval_seconds,
            log_info=log_info,
            log_error=log_error,
        )
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：API 需要复用同一个执行日志存储，任务运行和页面查询保持一致。
        # 影响范围：/execution-logs 和任务运行。
        self.execution_log_store = ExecutionLogStore(
            history_path=execution_log_path,
            export_dir=execution_log_export_dir,
        )
        # === MODIFIED END ===
    # === MODIFIED END ===

    def get_config(self) -> dict[str, object]:
        """Returns the active application configuration as API-safe data."""

        config = ConfigService().load(self.config_path)
        return serialize_config(config)

    # === MODIFIED START ===
    # 原因：支持通过 API 替换完整配置，由 application 层委托配置服务校验落盘。
    # 影响范围：配置维护接口。
    def replace_config(self, payload: dict[str, object]) -> dict[str, object]:
        """Replaces the active application configuration."""

        config = ConfigService().replace(self.config_path, payload)
        return serialize_config(config)

    def update_rule_config(self, payload: dict[str, object]) -> dict[str, object]:
        """Updates rule configuration fields and returns the saved config."""

        config = ConfigService().update_rules(self.config_path, payload)
        return serialize_config(config)

    def upload_region_xlsx(self, file_bytes: bytes, filename: str) -> dict[str, object]:
        """Parses an xlsx file, merges restricted regions into config (overwrite by key)."""

        parsed = load_restricted_regions_from_bytes(file_bytes, filename)
        if not parsed:
            raise ValueError("未能从文件中解析出任何限发区域记录")

        config_service = ConfigService()
        config = config_service.load(self.config_path)

        existing = list(config.rules.restricted_regions)
        before = len(existing)
        existing_map: dict[tuple[str, str, str], int] = {}
        for idx, region in enumerate(existing):
            key = (region.sku_code, region.province, region.city or "")
            existing_map[key] = idx

        added = 0
        modified = 0
        for item in parsed:
            sku_code = item["sku_code"]
            province = item["province"]
            city = item["city"] or ""
            key = (sku_code, province, city)
            if key in existing_map:
                existing[existing_map[key]] = RestrictedRegion(
                    sku_code=sku_code,
                    province=province,
                    city=item["city"],
                )
                modified += 1
            else:
                existing.append(RestrictedRegion(
                    sku_code=sku_code,
                    province=province,
                    city=item["city"],
                ))
                existing_map[key] = len(existing) - 1
                added += 1

        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        rules = data.setdefault("rules", {})
        rules["restricted_regions"] = [
            {
                "sku_code": r.sku_code,
                "province": r.province,
                "city": r.city,
                "district": r.district,
            }
            for r in existing
        ]
        config_service.save(self.config_path, config_service.from_dict(data))
        return {
            "count": len(parsed),
            "before": before,
            "added": added,
            "modified": modified,
            "total": len(existing),
        }

    def upload_sku_group_xlsx(self, file_bytes: bytes, filename: str) -> dict[str, object]:
        """Parses an xlsx file, merges SKU groups into config (upsert by SKU)."""

        parsed = load_sku_groups_from_bytes(file_bytes, filename)
        if not parsed:
            raise ValueError("未能从文件中解析出任何SKU群配置记录")

        config_service = ConfigService()
        config = config_service.load(self.config_path)

        existing = dict(config.rules.sku_group_map)
        before = len(existing)

        added = 0
        modified = 0
        for item in parsed:
            sku_code = item["sku_code"]
            group_name = item["group_name"]
            owner_mobile = item["owner_mobile"]
            if sku_code in existing:
                modified += 1
            else:
                added += 1
            existing[sku_code] = SkuGroupInfo(
                group_name=group_name,
                owner_mobile=owner_mobile,
            )

        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        rules = data.setdefault("rules", {})
        rules["sku_group_map"] = {
            sku: {"group_name": info.group_name, "owner_mobile": info.owner_mobile}
            for sku, info in existing.items()
        }
        config_service.save(self.config_path, config_service.from_dict(data))
        return {
            "count": len(parsed),
            "before": before,
            "added": added,
            "modified": modified,
            "total": len(existing),
        }

    def upload_excluded_sku_xlsx(self, file_bytes: bytes, filename: str) -> dict[str, object]:
        """Parses an xlsx file, merges SKUs into excluded_skus (union merge)."""

        parsed = load_skus_from_bytes(file_bytes, filename)
        if not parsed:
            raise ValueError("未能从文件中解析出任何SKU记录")

        config_service = ConfigService()
        config = config_service.load(self.config_path)

        existing = set(config.rules.excluded_skus)
        before = len(existing)
        added = 0
        for sku in parsed:
            if sku not in existing:
                existing.add(sku)
                added += 1

        merged = sorted(existing)

        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        rules = data.setdefault("rules", {})
        rules["excluded_skus"] = merged
        config_service.save(self.config_path, config_service.from_dict(data))
        return {
            "count": len(parsed),
            "before": before,
            "added": added,
            "modified": len(parsed) - added,
            "total": len(merged),
        }
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：接收方式待定时，先提供标准 SKU-供应商对照数据的查询和批量覆盖入口。
    # 影响范围：供应商映射 API。
    def get_supplier_mappings(self) -> dict[str, object]:
        """Returns current SKU to supplier mappings."""

        return suppliers_to_payload(self.supplier_mapping_store.load_items())

    def replace_supplier_mappings(self, payload: dict[str, object]) -> dict[str, object]:
        """Replaces SKU to supplier mappings synced from ERP."""

        items = self.supplier_mapping_store.replace_from_payload(payload)
        return suppliers_to_payload(items)
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：提供异常订单明细查询和下载能力。
    # 影响范围：异常订单 API。
    def list_exception_orders(self, limit: int = 100) -> dict[str, object]:
        """Returns recent exception order details."""

        return exception_orders_to_payload(self.exception_order_store.list_recent(limit))

    def export_exception_orders(self, trace_id: str | None = None) -> Path:
        """Exports persisted exception order details as a CSV file."""

        return self.exception_order_store.export_csv(
            trace_id=trace_id,
            supplier_client=self.supplier_client,
        )

    # === MODIFIED START ===
    # 原因：任务清单需要下载当前批次的正常推送订单明细。
    # 影响范围：任务下载接口服务。
    def export_pushed_orders(self, trace_id: str) -> Path:
        """Exports normal pushed order details for one task trace id."""

        return self.pushed_order_store.export_csv(trace_id)
    # === MODIFIED END ===
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：前端需要查询和下载面向业务人员的任务执行日志。
    # 影响范围：执行日志 API 服务。
    def list_execution_logs(
        self,
        limit: int | None = None,
        trace_id: str | None = None,
        stage: str | None = None,
        result: str | None = None,
        # === MODIFIED START ===
        # 原因：执行日志展示改为按周期查询，不再默认固定条数。
        # 影响范围：执行日志 API 服务。
        start_at: str | None = None,
        end_at: str | None = None,
        # === MODIFIED END ===
    ) -> dict[str, object]:
        """Returns recent visual execution logs."""

        return execution_logs_to_payload(
            self.execution_log_store.list_recent(
                limit=limit,
                trace_id=trace_id,
                stage=stage,
                result=result,
                start_at=start_at,
                end_at=end_at,
            )
        )

    def export_execution_logs(
        self,
        trace_id: str | None = None,
        stage: str | None = None,
        result: str | None = None,
        # === MODIFIED START ===
        # 原因：执行日志下载需要和页面周期筛选保持一致。
        # 影响范围：执行日志 API 服务。
        start_at: str | None = None,
        end_at: str | None = None,
        # === MODIFIED END ===
    ) -> Path:
        """Exports visual execution logs as a CSV file."""

        return self.execution_log_store.export_csv(
            trace_id=trace_id,
            stage=stage,
            result=result,
            start_at=start_at,
            end_at=end_at,
        )
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：支持任务付款状态查询和付款回执上传。
    # 影响范围：付款追踪 API。
    def get_payment_status(self, trace_id: str) -> dict[str, object]:
        """Returns payment status for one task."""

        return self.payment_receipt_store.to_payload(trace_id)

    def upload_payment_receipt(
        self,
        trace_id: str,
        original_filename: str,
        content: bytes,
    ) -> dict[str, object]:
        """Stores a payment receipt and returns paid status."""

        record = self.payment_receipt_store.save_receipt(
            trace_id=trace_id,
            original_filename=original_filename,
            content=content,
        )
        return payment_receipt_to_dict(record)
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：提供固定时间 Scheduler 状态查询和 tick 触发入口。
    # 影响范围：Scheduler API。
    def get_scheduler_status(self) -> dict[str, object]:
        """Returns current fixed-time scheduler status."""

        config = ConfigService().load(self.config_path)
        # === MODIFIED START ===
        # 原因：定时任务配置支持多条，状态接口需要返回每条配置状态并保留旧字段兼容。
        # 影响范围：/scheduler/status。
        return self._build_scheduler().status_many(config.schedules)
        # === MODIFIED END ===

    def tick_scheduler(self) -> dict[str, object]:
        """Runs one scheduler tick and returns whether a task was triggered."""

        config = ConfigService().load(self.config_path)
        # === MODIFIED START ===
        # 原因：定时任务配置支持多条，tick 需要逐条判断并运行所有到点任务。
        # 影响范围：/scheduler/tick 和后台 Scheduler loop。
        payload = self._build_scheduler().tick_many(config.schedules)
        summaries = payload.pop("summaries", [])
        payload["summaries"] = [self._summary_payload(summary) for summary in summaries]
        if payload["summaries"]:
            payload["summary"] = payload["summaries"][0]
        # === MODIFIED END ===
        return payload

    async def start_scheduler_loop(self) -> None:
        """Starts the background scheduler loop."""

        await self.scheduler_loop.start()

    async def stop_scheduler_loop(self) -> None:
        """Stops the background scheduler loop."""

        await self.scheduler_loop.stop()

    def get_scheduler_loop_status(self) -> dict[str, object]:
        """Returns background scheduler loop status."""

        loop_status = self.scheduler_loop.status()
        scheduler_status = self.get_scheduler_status()
        return {
            **loop_status,
            "scheduler": scheduler_status,
        }
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：任务来源已配置化，新增通用运行入口，mock-run 仅作为兼容别名。
    # 影响范围：/tasks/run、/tasks/mock-run 和 /tasks/latest。
    def run_task(self) -> dict[str, object]:
        """Runs one configured task and stores its summary."""

        summary = run_once(
            config_path=self.config_path,
            supplier_mapping_path=self.supplier_mapping_path,
            # === MODIFIED START ===
            # 原因：任务批次编码需要按当天历史批次做四位数累计。
            # 影响范围：tasks/run、tasks/mock-run 返回的 trace_id/task_id。
            existing_task_codes_provider=self.task_run_store.list_trace_ids,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：运行任务时同步持久化异常订单明细。
            # 影响范围：/tasks/run 和 /tasks/mock-run。
            exception_order_path=self.exception_order_path,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：运行任务时同步持久化正常推送订单明细。
            # 影响范围：任务清单正常订单下载。
            pushed_order_path=self.pushed_order_path,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：运行任务时同步持久化可视化执行日志。
            # 影响范围：执行日志页面与下载接口。
            execution_log_path=self.execution_log_store.history_path,
            # === MODIFIED END ===
        )
        self.task_run_store.append(summary)
        payload = self._summary_payload(summary)
        return payload

    def run_mock_task(self) -> dict[str, object]:
        """Runs one configured task through the backward-compatible mock-run endpoint."""

        return self.run_task()
    # === MODIFIED END ===

    def get_latest_summary(self) -> dict[str, object] | None:
        """Returns the latest configured task summary when available."""

        # === MODIFIED START ===
        # 原因：最新任务从持久化记录读取，避免服务重启丢失。
        # 影响范围：/tasks/latest。
        summary = self.task_run_store.latest()
        if summary is None:
            return None
        payload = self._summary_payload(summary)
        # === MODIFIED END ===
        return payload

    def list_recent_summaries(self, limit: int = 20) -> list[dict[str, object]]:
        """Returns recent task run summaries for API responses."""

        # === MODIFIED START ===
        # 原因：提供任务历史查询能力，接口层保持薄委托。
        # 影响范围：/tasks/history。
        payload = [self._summary_payload(summary) for summary in self.task_run_store.list_recent(limit)]
        # === MODIFIED END ===
        return payload

    # === MODIFIED START ===
    # 原因：任务摘要响应需要附带付款状态，上传回执后列表可直接显示已付款。
    # 影响范围：任务最新和历史接口响应。
    def _summary_payload(self, summary) -> dict[str, object]:
        """Converts a task run summary into an API payload with payment status."""

        # === MODIFIED START ===
        # 原因：任务摘要包含 Enum，API 响应需要返回稳定中文状态值。
        # 影响范围：/tasks/latest 和 /tasks/history。
        payload = run_summary_to_dict(summary)
        # === MODIFIED END ===
        payload["payment_status"] = self.payment_receipt_store.get_status(summary.trace_id).value
        return payload
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：Scheduler 需要调用与手动任务一致的运行和持久化流程。
    # 影响范围：Scheduler tick。
    def _build_scheduler(self) -> DailyFixedTimeScheduler:
        """Builds the fixed-time scheduler for API operations."""

        return DailyFixedTimeScheduler(
            state_store=self.scheduler_state_store,
            task_runner=self._run_configured_task,
            task_recorder=self.task_run_store.append,
        )

    def _run_configured_task(self):
        """Runs one configured task without recording the summary."""

        return run_once(
            config_path=self.config_path,
            supplier_mapping_path=self.supplier_mapping_path,
            # === MODIFIED START ===
            # 原因：定时任务与手动任务共用同一批次号累计规则。
            # 影响范围：Scheduler tick 触发的任务 trace_id/task_id。
            existing_task_codes_provider=self.task_run_store.list_trace_ids,
            # === MODIFIED END ===
            exception_order_path=self.exception_order_path,
            # === MODIFIED START ===
            # 原因：定时任务运行也需要持久化正常推送订单明细。
            # 影响范围：Scheduler 触发任务的正常订单下载。
            pushed_order_path=self.pushed_order_path,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：定时任务运行也需要持久化可视化执行日志。
            # 影响范围：执行日志页面与下载接口。
            execution_log_path=self.execution_log_store.history_path,
            # === MODIFIED END ===
        )

    def _scheduler_loop_interval_seconds(self) -> int:
        """Returns the current configured scheduler loop interval."""

        config = ConfigService().load(self.config_path)
        # === MODIFIED START ===
        # 原因：多条定时任务配置下后台检查间隔取所有配置中的最小值，避免漏掉更频繁的配置。
        # 影响范围：Scheduler loop interval。
        return min(schedule.check_interval_seconds for schedule in config.schedules)
        # === MODIFIED END ===
    # === MODIFIED END ===


def serialize_config(config: AppConfig) -> dict[str, object]:
    """Converts AppConfig into JSON-compatible data."""

    # === MODIFIED START ===
    # 原因：配置序列化逻辑收敛到 ConfigService，避免保存和返回字段不一致。
    # 影响范围：/config 及配置更新接口响应。
    payload = to_dict(config)
    # === MODIFIED END ===
    return payload
