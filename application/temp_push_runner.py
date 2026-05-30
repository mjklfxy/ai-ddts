from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from application.config_service import AppConfig, ConfigService
from application.exception_order_store import ExceptionOrderStore
from application.execution_log_store import ExecutionLogRecord, ExecutionLogStore
from application.file_generator import ExcelFileGenerator
from application.manual_runner import (
    _build_cached_user_resolver,
    _build_upload_fn,
    build_message_sender_from_config,
    build_order_source_client,
    fetch_orders_from_config,
)
from application.order_splitter import GroupOrderBatch, OrderLineForSplit, OrderSplitter
from application.pipeline import (
    Pipeline,
    PipelineBatchDelivery,
    PipelineBatchFailure,
    PipelineOrder,
    PipelineOrderEvaluation,
)
from application.special_push_order_store import SpecialPushOrderStore
from domain.enums.execution_log import ExecutionLogResult, ExecutionLogStage
from domain.enums.rule import RuleDecision
from domain.enums.status import KingdeeStatus, PushStatus
from domain.exception_order import ExceptionOrder, ExceptionOrderSource
from domain.rule_engine import RuleEngine
from domain.rules.base import RuleContext, RuleResult
from domain.rules.group_rule import GroupRule
from domain.rules.region_rule import RegionRule
from domain.rules.special_sku_rule import SpecialSkuRule
from infrastructure.cloud_warehouse_client import CloudWarehouseClient
from infrastructure.message_adapter import MessagePayload
from infrastructure.qixin_client import build_download_url
from shared.env import resolve_config_path
from shared.logging.logger import log_error, log_info


def run_temp_push(
    window_start: datetime,
    # === MODIFIED START ===
    # 原因：结束时间改为从定时任务 run_at 计算，不再依赖任务运行历史 trace_id。
    # 影响范围：临时推送执行逻辑、函数签名。
    window_end_run_at: str,
    # === MODIFIED END ===
    config_path: str | Path | None = None,
    supplier_mapping_path: str | Path = Path("outputs") / "sku_supplier_mappings.json",
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Runs one temporary push with a 3-rule engine (SpecialSku + Region + Group)."""

    if config_path is None:
        config_path = resolve_config_path()
    config = ConfigService().load(config_path)
    now = (clock or datetime.now)()

    # === MODIFIED START ===
    # 原因：从 run_at 计算 window_end，复用 manual_runner 的逻辑。
    # 影响范围：临时推送时间窗口计算。
    window_end = _scheduled_window_end(now, window_end_run_at)
    # === MODIFIED END ===

    # 2. Generate temp_push_id
    temp_push_id = f"TP-{now:%Y%m%d%H%M%S}"

    # 3. Create task context for logging
    from application.task_service import TaskService
    task_context = TaskService(clock=lambda: now).create_task(
        task_name=f"临时推送-{temp_push_id}",
        window_start=window_start,
        window_end=window_end,
    )

    # 4. Setup stores and logs
    base_dir = Path("outputs") / "special_push" / temp_push_id
    order_store = SpecialPushOrderStore(temp_push_id=temp_push_id)
    log_store = ExecutionLogStore(history_path=base_dir / "execution_logs.json")
    exception_store = ExceptionOrderStore(history_path=base_dir / "exception_orders.json")

    _append_log(log_store, task_context, ExecutionLogStage.TEMP_PUSH, ExecutionLogResult.SUCCESS,
                "临时推送开始",
                impact=f"时间窗口：{window_start.isoformat()} 至 {window_end.isoformat()}",
                details={"temp_push_id": temp_push_id, "window_end_run_at": window_end_run_at,
                         "window_start": window_start.isoformat(), "window_end": window_end.isoformat()})

    # 5. Fetch orders
    try:
        orders = fetch_orders_from_config(config=config, task_context=task_context)
    except Exception as exc:
        _append_log(log_store, task_context, ExecutionLogStage.FETCH, ExecutionLogResult.FAILED,
                    "订单抓取失败", impact="本次临时推送没有拿到订单数据。",
                    suggestion="检查订单来源配置、吉客云凭据、网络连通性和时间窗口。",
                    details={"error_type": exc.__class__.__name__, "reason": str(exc)[:500]})
        raise

    _append_log(log_store, task_context, ExecutionLogStage.FETCH, ExecutionLogResult.SUCCESS,
                "已完成订单抓取", impact=f"本次抓取订单 {len(orders)} 单",
                details={"order_count": len(orders)})

    # 6. Build 3-rule engine (SpecialSku → Region → Group)
    rule_engine = RuleEngine(rules=[
        SpecialSkuRule(
            special_skus=set(config.rules.special_skus),
        ),
        RegionRule(
            restricted_regions=config.rules.restricted_regions,
            enabled=config.rules.restricted_regions_enabled,
        ),
        GroupRule(
            sku_group_map=config.rules.sku_group_map,
            enabled=config.rules.sku_group_map_enabled,
        ),
    ], log_info=log_info)

    # 7. Evaluate orders
    passed_orders, ignored_orders, error_orders, exception_orders, passed_lines = _evaluate_orders(
        task_context=task_context,
        orders=orders,
        rule_engine=rule_engine,
    )

    _append_log(log_store, task_context, ExecutionLogStage.RULE, ExecutionLogResult.SUCCESS,
                "规则判断完成",
                impact=f"正选通过 {len(passed_orders)} 单，忽略 {len(ignored_orders)} 单，异常 {len(error_orders)} 单",
                details={"passed": len(passed_orders), "ignored": len(ignored_orders), "error": len(error_orders)})

    # 8. Store exception orders + generate error files
    if exception_orders:
        exception_store.append_many(task_context=task_context, exception_orders=exception_orders)
        # === MODIFIED START ===
        # 原因：异常订单需要按厂家生成 error Excel 文件，供业务人员查看和处理。
        # 影响范围：outputs/special_push/{id}/error/ 目录。
        # 注意：ExcelFileGenerator.generate_error() 内部会自动拼 /error/ 子目录，
        #       所以这里传 base_dir 而非 base_dir / "error"，避免双层嵌套。
        from application.manual_runner import _generate_error_files
        _generate_error_files(
            exception_orders=exception_orders,
            output_dir=base_dir,
            clock=lambda: now,
        )
        # === MODIFIED END ===

    # 9. Split and deliver
    deliveries: tuple[PipelineBatchDelivery, ...] = ()
    batch_failures: tuple[PipelineBatchFailure, ...] = ()
    push_status = PushStatus.PENDING

    if passed_lines:
        splitter = OrderSplitter(sku_group_map=config.rules.sku_group_map)
        batches = splitter.split(tuple(passed_lines))

        file_generator = ExcelFileGenerator(
            output_dir=base_dir / "order_files",
            clock=lambda: now,
        )
        message_sender = build_message_sender_from_config(config)
        user_resolver = _build_cached_user_resolver(config)

        deliveries, batch_failures = _deliver_batches(
            task_context=task_context,
            batches=batches,
            file_generator=file_generator,
            message_sender=message_sender,
            # === MODIFIED START ===
            # 原因：临时推送文件名加 temp_push_id 前缀，与定时任务产出的文件区分。
            # 影响范围：临时推送正常订单 Excel 文件名。
            file_prefix=f"{temp_push_id}_",
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：临时推送在文件直推模式下也必须先得到公网 file_url，否则 QixinSender 会拒绝发送。
            # 影响范围：临时推送推送群阶段。
            upload_file=_build_upload_fn(config),
            download_base_url=config.download.base_url or None,
            download_secret_key=os.environ.get(config.download.secret_key_env),
            # === MODIFIED END ===
            user_resolver=user_resolver,
            log_info=log_info,
            log_error=log_error,
        )

        if batch_failures and deliveries:
            push_status = PushStatus.PARTIAL
        elif batch_failures:
            push_status = PushStatus.FAILED
        elif deliveries:
            push_status = PushStatus.SUCCESS

    # 10. Store pushed orders
    if deliveries:
        order_store.append_many(task_context=task_context, deliveries=deliveries)

    # 11. Final log
    _append_log(log_store, task_context, ExecutionLogStage.MESSAGE,
                _push_result(push_status),
                _push_summary(push_status),
                impact=f"推送状态：{push_status.value}；成功批次 {len(deliveries)} 个",
                details={"push_status": push_status.value, "delivery_count": len(deliveries)})

    return {
        "temp_push_id": temp_push_id,
        "trace_id": task_context.trace_id,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "passed_count": len(passed_orders),
        "ignored_count": len(ignored_orders),
        "error_count": len(error_orders),
        "delivery_count": len(deliveries),
        "push_status": push_status.value,
    }


def _evaluate_orders(
    task_context,
    orders: tuple[PipelineOrder, ...] | list[PipelineOrder],
    rule_engine: RuleEngine,
):
    """Evaluates orders using the temporary rule engine."""
    passed_orders: list[PipelineOrderEvaluation] = []
    ignored_orders: list[PipelineOrderEvaluation] = []
    error_orders: list[PipelineOrderEvaluation] = []
    exception_orders: list[ExceptionOrder] = []
    passed_lines: list[OrderLineForSplit] = []

    for order in orders:
        engine_result = rule_engine.evaluate(order.rule_context)
        evaluation = PipelineOrderEvaluation(
            order_no=order.rule_context.order_no,
            engine_result=engine_result,
        )

        if engine_result.is_pass:
            passed_orders.append(evaluation)
            passed_lines.extend(order.order_lines)
        elif engine_result.is_ignore:
            ignored_orders.append(evaluation)
        else:
            error_orders.append(evaluation)
            for order_line in order.order_lines:
                exception_orders.append(
                    ExceptionOrder.from_rule_result(
                        source=ExceptionOrderSource(
                            order_no=order_line.order_no,
                            sku_code=order_line.sku_code,
                            delivery_order_no=order_line.delivery_order_no,
                            goods_summary=order_line.goods_summary,
                            warehouse_code=order_line.warehouse_code,
                            warehouse_name=order_line.warehouse_name,
                            quantity=order_line.quantity,
                            receiver_name=order_line.receiver_name,
                            address=order_line.address,
                            phone=order_line.phone,
                            logistics_company=order_line.logistics_company,
                            logistics_no=order_line.logistics_no,
                            group_name=order_line.group_name,
                            owner_mobile=order_line.owner_mobile,
                            supplier_name=order_line.supplier_name,
                        ),
                        rule_result=engine_result.final_result,
                    )
                )

    return passed_orders, ignored_orders, error_orders, tuple(exception_orders), passed_lines


def _deliver_batches(
    task_context,
    batches: tuple[GroupOrderBatch, ...],
    file_generator: ExcelFileGenerator,
    message_sender,
    file_prefix: str = "",
    # === MODIFIED START ===
    # 原因：临时推送需要与正式 pipeline 一样把生成文件上传/签名为公网 URL，供文件直推使用。
    # 影响范围：临时推送 _deliver_batches 与 MessagePayload.file_url。
    upload_file: Callable[[Path], str] | None = None,
    download_base_url: str | None = None,
    download_secret_key: str | None = None,
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：user_id 解析对齐主流程，使用带缓存的 resolver 替代内联硬编码。
    # 影响范围：临时推送 _deliver_batches user_id 解析。
    user_resolver: Callable[[str], str] | None = None,
    # === MODIFIED END ===
    log_info=None,
    log_error=None,
):
    """Delivers batches with optional file prefix."""
    deliveries: list[PipelineBatchDelivery] = []
    failures: list[PipelineBatchFailure] = []

    for batch in batches:
        generated_file = None
        try:
            generated_file = file_generator.generate(batch, file_prefix=file_prefix)
            # === MODIFIED START ===
            # 原因：push_mode=file 时祺信接口要求 file_url，临时推送原先只传本地 file_path 导致推送失败。
            # 影响范围：临时推送文件上传/下载 URL 构造与消息发送。
            file_url = None
            if upload_file is not None:
                file_url = upload_file(generated_file.file_path)
                if log_info is not None:
                    log_info("temp_push_file_uploaded", {
                        "trace_id": task_context.trace_id,
                        "group_name": batch.group_name,
                        "file_name": generated_file.file_path.name,
                        "has_file_url": bool(file_url),
                    })
            elif download_base_url and download_secret_key:
                file_url = build_download_url(
                    base_url=download_base_url,
                    filename=generated_file.file_path.name,
                    secret_key=download_secret_key,
                )
            # === MODIFIED END ===

            # === MODIFIED START ===
            # 原因：user_id 解析对齐主流程，使用带缓存的 resolver 替代内联硬编码。
            # 影响范围：临时推送 user_id 解析。
            user_id = batch.user_id
            if not user_id and batch.owner_mobile and user_resolver is not None:
                try:
                    user_id = user_resolver(batch.owner_mobile)
                except Exception:
                    user_id = batch.owner_mobile
            # === MODIFIED END ===

            message_result = message_sender.send_file(
                MessagePayload(
                    trace_id=task_context.trace_id,
                    group_name=batch.group_name,
                    owner_mobile=batch.owner_mobile,
                    user_id=user_id or "",
                    file_path=generated_file.file_path,
                    # === MODIFIED START ===
                    # 原因：临时推送文件直推需要透传上传或签名后的公网文件 URL。
                    # 影响范围：祺信文件直推 MessagePayload。
                    file_url=file_url,
                    # === MODIFIED END ===
                )
            )
            deliveries.append(PipelineBatchDelivery(
                batch=batch,
                generated_file=generated_file,
                message_result=message_result,
            ))
        except Exception as exc:
            failures.append(PipelineBatchFailure(
                batch=batch,
                group_name=batch.group_name,
                file_path=str(generated_file.file_path) if generated_file else "",
                reason=str(exc)[:500],
            ))

    return tuple(deliveries), tuple(failures)


def _append_log(store, task_context, stage, result, summary, impact="", suggestion="", details=None):
    store.append(ExecutionLogRecord(
        created_at=datetime.now().isoformat(),
        trace_id=task_context.trace_id,
        task_name=task_context.task_name,
        stage=stage,
        result=result,
        summary=summary,
        impact=impact,
        suggestion=suggestion,
        details=details or {},
    ))


def _push_result(status: PushStatus) -> ExecutionLogResult:
    if status is PushStatus.SUCCESS:
        return ExecutionLogResult.SUCCESS
    if status is PushStatus.PARTIAL:
        return ExecutionLogResult.PARTIAL
    if status is PushStatus.FAILED:
        return ExecutionLogResult.FAILED
    return ExecutionLogResult.SKIPPED


def _push_summary(status: PushStatus) -> str:
    if status is PushStatus.SUCCESS:
        return "临时推送完成"
    if status is PushStatus.PARTIAL:
        return "临时推送部分成功"
    if status is PushStatus.FAILED:
        return "临时推送失败"
    return "没有需要推送的订单"


def _scheduled_window_end(now: datetime, run_at: str) -> datetime:
    """Returns today's scheduled end time for one fixed daily schedule."""

    scheduled_time = datetime.strptime(run_at, "%H:%M").time()
    return datetime.combine(now.date(), scheduled_time)
