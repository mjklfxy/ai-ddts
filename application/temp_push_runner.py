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
from application.task_run_store import TaskRunStore
from domain.enums.execution_log import ExecutionLogResult, ExecutionLogStage
from domain.enums.rule import RuleDecision
from domain.enums.status import KingdeeStatus, PushStatus
from domain.exception_order import ExceptionOrder, ExceptionOrderSource
from domain.rule_engine import RuleEngine
from domain.rules.base import RuleContext, RuleResult
from domain.rules.group_rule import GroupRule
from domain.rules.special_sku_rule import SpecialSkuRule
from infrastructure.cloud_warehouse_client import CloudWarehouseClient
from infrastructure.message_adapter import MessagePayload
from shared.env import resolve_config_path
from shared.logging.logger import log_error, log_info


def run_temp_push(
    window_start: datetime,
    window_end_trace_id: str,
    config_path: str | Path = resolve_config_path(),
    supplier_mapping_path: str | Path = Path("outputs") / "sku_supplier_mappings.json",
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Runs one temporary push with a 2-rule engine (SpecialSku + GroupRule)."""

    config = ConfigService().load(config_path)
    now = (clock or datetime.now)()

    # 1. Read window_end from existing task
    task_run_store = TaskRunStore()
    end_summary = task_run_store.get_by_trace_id(window_end_trace_id)
    if end_summary is None or not end_summary.window_end:
        raise ValueError(f"任务 {window_end_trace_id} 不存在或缺少时间窗口信息")
    window_end = datetime.fromisoformat(end_summary.window_end)

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
                details={"temp_push_id": temp_push_id, "window_end_trace_id": window_end_trace_id})

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

    # 6. Build 2-rule engine
    rule_engine = RuleEngine(rules=[
        SpecialSkuRule(
            special_skus=set(config.rules.special_skus),
            enabled=config.rules.special_skus_enabled,
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
        from application.manual_runner import _generate_error_files
        _generate_error_files(
            exception_orders=exception_orders,
            output_dir=base_dir / "error",
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

        deliveries, batch_failures = _deliver_batches(
            task_context=task_context,
            batches=batches,
            file_generator=file_generator,
            message_sender=message_sender,
            file_prefix="special_",
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

            user_id = batch.user_id
            if not user_id and batch.owner_mobile:
                try:
                    from infrastructure.qixin_client import RemoteUserResolver
                    resolver = RemoteUserResolver(
                        api_url="http://mengyang.renruikeji.cn/api/userid",
                        timeout_seconds=30,
                    )
                    user_id = resolver.get_userid_by_mobile(batch.owner_mobile)
                except Exception:
                    user_id = batch.owner_mobile

            message_result = message_sender.send_file(
                MessagePayload(
                    trace_id=task_context.trace_id,
                    group_name=batch.group_name,
                    owner_mobile=batch.owner_mobile,
                    user_id=user_id or "",
                    file_path=generated_file.file_path,
                    file_url=None,
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
