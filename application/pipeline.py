from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

# === MODIFIED START ===
# 原因：推送/上传订单文件统一改为 Excel。
# 影响范围：Pipeline 文件生成器依赖类型。
from application.file_generator import ExcelFileGenerator, GeneratedFile
# === MODIFIED END ===
from application.order_splitter import GroupOrderBatch, OrderLineForSplit, OrderSplitter
from application.task_service import TaskContext
from domain.enums.rule import RuleDecision
from domain.enums.status import KingdeeStatus, PushStatus
from domain.exception_order import ExceptionOrder, ExceptionOrderSource
from domain.rule_engine import RuleEngine, RuleEngineResult
from domain.rules.base import RuleContext, RuleResult
from infrastructure.message_adapter import MessagePayload, MessageSendResult
# === MODIFIED START ===
# 原因：文件直推模式需要为每个文件构造签名下载地址。
# 影响范围：Pipeline._deliver_batches。
from infrastructure.qixin_client import build_download_url
# === MODIFIED END ===
# === MODIFIED START ===
# 原因：文件生成后需要上传到公网文件服务器供群消息使用。
# 影响范围：Pipeline._deliver_batches。
from collections.abc import Callable
from pathlib import Path

UploadFileFn = Callable[[Path], str] | None
# === MODIFIED END ===


LogInfo = Protocol


class PipelineLogInfo(Protocol):
    """Callable protocol for pipeline info logs."""

    def __call__(self, event: str, payload: dict[str, object]) -> None:
        """Record a pipeline info event."""


class PipelineLogError(Protocol):
    """Callable protocol for pipeline error logs."""

    def __call__(self, event: str, payload: dict[str, object]) -> None:
        """Record a pipeline error event."""


class MessageSender(Protocol):
    """Message sender dependency used by the pipeline."""

    def send_file(self, payload: MessagePayload) -> MessageSendResult:
        """Send one generated file to a group."""


class KingdeeService(Protocol):
    """Kingdee dependency used by the pipeline after successful pushes."""

    def submit_purchase_request(
        self,
        task_context: TaskContext,
        deliveries: tuple["PipelineBatchDelivery", ...],
    ) -> str:
        """Submit pushed task summary data and return a tracking id."""


@dataclass(frozen=True, slots=True)
class PipelineOrder:
    """Order aggregate passed into the pipeline after source adaptation."""

    rule_context: RuleContext
    order_lines: tuple[OrderLineForSplit, ...]


@dataclass(frozen=True, slots=True)
class PipelineOrderEvaluation:
    """Rule evaluation result attached to one pipeline order."""

    order_no: str
    engine_result: RuleEngineResult


# === MODIFIED START ===
# 原因：整单异常会连带同订单其他 SKU 进入异常明细，需要保留真正触发 ERROR 的 SKU 和规则结果。
# 影响范围：Pipeline 规则异常明细原因生成。
@dataclass(frozen=True, slots=True)
class PipelineLineRuleFailure:
    """Rule failure identified by re-evaluating one SKU line in an errored order."""

    sku_code: str
    rule_result: RuleResult
# === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class PipelineBatchDelivery:
    """Successful file generation and message delivery for one group batch."""

    batch: GroupOrderBatch
    generated_file: GeneratedFile
    message_result: MessageSendResult


# === MODIFIED START ===
# 原因：厂家群推送可能部分成功、部分失败，需要记录失败批次用于判定“部分推送”状态。
# 影响范围：Pipeline 推送阶段状态判定和失败摘要。
@dataclass(frozen=True, slots=True)
class PipelineBatchFailure:
    """Failed file generation or message delivery for one group batch."""

    # === MODIFIED START ===
    # 原因：推送群失败需要生成异常订单明细，失败对象必须保留批次订单行。
    # 影响范围：PipelineBatchFailure 和异常订单生成。
    batch: GroupOrderBatch
    # === MODIFIED END ===
    group_name: str
    file_path: str
    reason: str
# === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    """Final pipeline orchestration result."""

    task_context: TaskContext
    passed_orders: tuple[PipelineOrderEvaluation, ...]
    ignored_orders: tuple[PipelineOrderEvaluation, ...]
    error_orders: tuple[PipelineOrderEvaluation, ...]
    # === MODIFIED START ===
    # 原因：异常订单需要从 pipeline 输出，供后续持久化查询和下载。
    # 影响范围：PipelineRunResult。
    exception_orders: tuple[ExceptionOrder, ...]
    # === MODIFIED END ===
    deliveries: tuple[PipelineBatchDelivery, ...]
    kingdee_tracking_id: str | None
    # === MODIFIED START ===
    # 原因：任务历史需要持久化推送和金蝶提交状态，供前端追踪。
    # 影响范围：Pipeline 输出和 RunSummary 构建。
    push_status: PushStatus
    kingdee_status: KingdeeStatus
    failure_stage: str | None = None
    failure_reason: str | None = None
    # === MODIFIED END ===


class Pipeline:
    """Orchestrates rule filtering, splitting, file generation, push, and Kingdee submission."""

    def __init__(
        self,
        rule_engine: RuleEngine,
        order_splitter: OrderSplitter,
        file_generator: ExcelFileGenerator,
        message_sender: MessageSender,
        kingdee_service: KingdeeService,
        # === MODIFIED START ===
        # 原因：金蝶推送是可关闭的集成阶段，pipeline 需要按配置跳过提交。
        # 影响范围：Pipeline 金蝶阶段编排。
        kingdee_enabled: bool = True,
        # === MODIFIED START ===
        # 原因：祺信文件直推模式需要知道文件的公网下载地址，由调用方注入。
        # 影响范围：Pipeline._deliver_batches、MessagePayload.file_url。
        download_base_url: str | None = None,
        download_secret_key: str | None = None,
        # === MODIFIED START ===
        # 原因：文件生成后需要上传到公网文件服务器供群消息推送使用。
        # 影响范围：Pipeline._deliver_batches。
        upload_file: UploadFileFn = None,
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：user_id 改为推送时惰性解析，避免构建阶段串行调用 API 导致卡死。
        # 影响范围：Pipeline._deliver_batches。
        user_resolver: Callable[[str], str] | None = None,
        # === MODIFIED END ===
        log_info: PipelineLogInfo | None = None,
        log_error: PipelineLogError | None = None,
    ) -> None:
        if not isinstance(kingdee_enabled, bool):
            raise ValueError("kingdee_enabled must be a boolean")
        self.rule_engine = rule_engine
        self.order_splitter = order_splitter
        self.file_generator = file_generator
        self.message_sender = message_sender
        self.kingdee_service = kingdee_service
        # === MODIFIED START ===
        # 原因：保存金蝶启用状态供运行阶段决定是否提交采购申请。
        # 影响范围：Pipeline.run。
        self.kingdee_enabled = kingdee_enabled
        # === MODIFIED START ===
        # 原因：祺信文件直推模式需要知道文件的公网下载地址，由调用方注入。
        # 影响范围：Pipeline._deliver_batches、MessagePayload.file_url。
        self.download_base_url = download_base_url
        self.download_secret_key = download_secret_key
        self.upload_file = upload_file
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：user_id 改为推送时惰性解析。
        # 影响范围：Pipeline._deliver_batches。
        self.user_resolver = user_resolver
        # === MODIFIED END ===
        self.log_info = log_info or self._noop_log
        self.log_error = log_error or self._noop_log

    def run(
        self,
        task_context: TaskContext,
        orders: tuple[PipelineOrder, ...] | list[PipelineOrder],
    ) -> PipelineRunResult:
        self._log_info(task_context.trace_id, "pipeline_start", {"order_count": len(orders)})

        try:
            # === MODIFIED START ===
            # 原因：规则失败订单需要生成异常订单明细。
            # 影响范围：pipeline 评估阶段返回值。
            passed_orders, ignored_orders, error_orders, exception_orders, passed_lines = self._evaluate_orders(
                task_context=task_context,
                orders=orders,
            )
            # === MODIFIED END ===
            batches = self.order_splitter.split(tuple(passed_lines))
            self._log_info(
                task_context.trace_id,
                "pipeline_split_done",
                {"batch_count": len(batches)},
            )

            # === MODIFIED START ===
            # 原因：推送失败需要形成可持久化任务状态，而不是只抛出 500。
            # 影响范围：Pipeline 任务状态输出。
            deliveries: tuple[PipelineBatchDelivery, ...] = ()
            kingdee_tracking_id: str | None = None
            push_status = PushStatus.PENDING
            kingdee_status = KingdeeStatus.PENDING
            failure_stage: str | None = None
            failure_reason: str | None = None

            # === MODIFIED START ===
            # 原因：推送到多个厂家群时可能出现部分成功，不能因为一个批次失败就丢掉已成功批次。
            # 影响范围：Pipeline 推送状态、正常推送明细持久化和金蝶提交数据范围。
            batch_failures: tuple[PipelineBatchFailure, ...] = ()
            deliveries, batch_failures = self._deliver_batches(task_context, batches)
            # === MODIFIED START ===
            # 原因：推送群失败需要计入异常订单明细，供任务下载和异常数统计。
            # 影响范围：PipelineRunResult.exception_orders 与任务异常统计。
            if batch_failures:
                exception_orders.extend(self._exception_orders_for_batch_failures(batch_failures))
            # === MODIFIED END ===
            if batches and batch_failures and deliveries:
                push_status = PushStatus.PARTIAL
                failure_stage = "message_push"
                failure_reason = _batch_failure_reason(batch_failures)
                self._log_error(
                    task_context.trace_id,
                    "pipeline_message_partial_failed",
                    {
                        "success_count": len(deliveries),
                        "failure_count": len(batch_failures),
                        "failure_stage": failure_stage,
                    },
                )
            elif batches and batch_failures:
                push_status = PushStatus.FAILED
                failure_stage = "message_push"
                failure_reason = _batch_failure_reason(batch_failures)
                self._log_error(
                    task_context.trace_id,
                    "pipeline_message_failed",
                    {
                        "failure_count": len(batch_failures),
                        "failure_stage": failure_stage,
                    },
                )
            elif batches:
                push_status = PushStatus.SUCCESS
            # === MODIFIED END ===

            # === MODIFIED START ===
            # 原因：当前默认不启用金蝶推送；未启用时只跳过金蝶阶段，不影响外部群推送结果。
            # 影响范围：Pipeline 金蝶状态和任务历史。
            if not self.kingdee_enabled:
                kingdee_status = KingdeeStatus.DISABLED
                self._log_info(
                    task_context.trace_id,
                    "pipeline_kingdee_disabled",
                    {"reason": "kingdee_disabled"},
                )
            elif push_status is not PushStatus.FAILED:
            # === MODIFIED END ===
                try:
                    kingdee_tracking_id = self._submit_kingdee(task_context, deliveries)
                    if kingdee_tracking_id is not None:
                        kingdee_status = KingdeeStatus.SUCCESS
                except Exception as exc:
                    kingdee_status = KingdeeStatus.FAILED
                    # === MODIFIED START ===
                    # 原因：部分推送时需优先保留推送失败提醒，避免任务列表失去“部分推送”的详情线索。
                    # 影响范围：PipelineRunResult.failure_stage/failure_reason。
                    if push_status is not PushStatus.PARTIAL:
                        failure_stage = "kingdee_submit"
                        failure_reason = _failure_reason(exc)
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：SKU-供应商对照缺失只影响金蝶提交状态，不计入异常订单。
                    # 影响范围：Pipeline 金蝶失败分支与异常订单输出。
                    # === MODIFIED END ===
                    self._log_error(
                        task_context.trace_id,
                        "pipeline_kingdee_failed",
                        {
                            "error_type": exc.__class__.__name__,
                            "failure_stage": failure_stage,
                        },
                    )
            # === MODIFIED END ===
            self._log_info(
                task_context.trace_id,
                "pipeline_finished",
                {
                    "passed_count": len(passed_orders),
                    "ignored_count": len(ignored_orders),
                    "error_count": len(error_orders),
                    "exception_order_count": len(exception_orders),
                    "delivery_count": len(deliveries),
                    "kingdee_submitted": kingdee_tracking_id is not None,
                    # === MODIFIED START ===
                    # 原因：pipeline 完成日志需要带出最终任务状态，便于排障。
                    # 影响范围：核心流程日志。
                    "push_status": push_status.value,
                    "kingdee_status": kingdee_status.value,
                    "failure_stage": failure_stage,
                    # === MODIFIED END ===
                },
            )
        except Exception as exc:
            self._log_error(
                task_context.trace_id,
                "pipeline_failed",
                {"error_type": exc.__class__.__name__},
            )
            raise

        return PipelineRunResult(
            task_context=task_context,
            passed_orders=tuple(passed_orders),
            ignored_orders=tuple(ignored_orders),
            error_orders=tuple(error_orders),
            # === MODIFIED START ===
            # 原因：将异常订单明细随 pipeline 结果返回给应用层持久化。
            # 影响范围：PipelineRunResult 构造。
            exception_orders=tuple(exception_orders),
            # === MODIFIED END ===
            deliveries=tuple(deliveries),
            kingdee_tracking_id=kingdee_tracking_id,
            # === MODIFIED START ===
            # 原因：将推送和金蝶状态随 pipeline 结果返回给应用层持久化。
            # 影响范围：PipelineRunResult 构造。
            push_status=push_status,
            kingdee_status=kingdee_status,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            # === MODIFIED END ===
        )

    def _evaluate_orders(
        self,
        task_context: TaskContext,
        orders: tuple[PipelineOrder, ...] | list[PipelineOrder],
    ) -> tuple[
        list[PipelineOrderEvaluation],
        list[PipelineOrderEvaluation],
        list[PipelineOrderEvaluation],
        list[ExceptionOrder],
        list[OrderLineForSplit],
    ]:
        passed_orders: list[PipelineOrderEvaluation] = []
        ignored_orders: list[PipelineOrderEvaluation] = []
        error_orders: list[PipelineOrderEvaluation] = []
        exception_orders: list[ExceptionOrder] = []
        passed_lines: list[OrderLineForSplit] = []

        for order in orders:
            engine_result = self.rule_engine.evaluate(order.rule_context)
            evaluation = PipelineOrderEvaluation(
                order_no=order.rule_context.order_no,
                engine_result=engine_result,
            )

            if engine_result.is_pass:
                passed_orders.append(evaluation)
                passed_lines.extend(order.order_lines)
                self._log_info(
                    task_context.trace_id,
                    "pipeline_order_pass",
                    {"order_no": order.rule_context.order_no},
                )
            elif engine_result.is_ignore:
                ignored_orders.append(evaluation)
                self._log_info(
                    task_context.trace_id,
                    "pipeline_order_ignore",
                    {"order_no": order.rule_context.order_no},
                )
            else:
                error_orders.append(evaluation)
                # === MODIFIED START ===
                # 原因：规则失败代表整单异常，将订单行转为可查询/可下载的异常明细。
                # 影响范围：异常订单生成。
                # 原因：连坐异常行需要写明同订单中真正触发异常的 SKU 和原因。
                # 影响范围：异常订单 reason 字段。
                exception_orders.extend(
                    self._exception_orders_for_rule_failure(
                        order=order,
                        engine_result=engine_result,
                    )
                )
                # === MODIFIED END ===
                self._log_info(
                    task_context.trace_id,
                    "pipeline_order_error",
                    {
                        "order_no": order.rule_context.order_no,
                        "rule_name": engine_result.final_result.rule_name,
                        "reason": engine_result.final_result.reason,
                    },
                )

        return passed_orders, ignored_orders, error_orders, exception_orders, passed_lines

    # === MODIFIED START ===
    # 原因：整单异常生成明细时，需要区分“本 SKU 真异常”和“同订单其他 SKU 异常导致连坐”。
    # 影响范围：Pipeline 规则异常明细 reason。
    def _exception_orders_for_rule_failure(
        self,
        order: PipelineOrder,
        engine_result: RuleEngineResult,
    ) -> tuple[ExceptionOrder, ...]:
        """Builds exception details and annotates co-order rows with root SKU failures."""

        line_failures = self._line_rule_failures(order)
        if not line_failures:
            return tuple(
                ExceptionOrder.from_rule_result(
                    source=self._exception_source_from_order_line(order_line),
                    rule_result=engine_result.final_result,
                )
                for order_line in order.order_lines
            )

        failures_by_sku = {failure.sku_code: failure for failure in line_failures}
        failure_summary = _line_failure_summary(line_failures)
        co_order_rule_result = RuleResult(
            decision=RuleDecision.ERROR,
            rule_name=engine_result.final_result.rule_name,
            reason=f"同订单其他SKU异常：{failure_summary}"[:500],
            message=(
                f"Order {order.rule_context.order_no} failed because other SKU lines "
                f"failed rules: {failure_summary}."
            ),
        )

        exception_orders: list[ExceptionOrder] = []
        for order_line in order.order_lines:
            sku_code = order_line.sku_code.strip()
            failure = failures_by_sku.get(sku_code)
            exception_orders.append(
                ExceptionOrder.from_rule_result(
                    source=self._exception_source_from_order_line(order_line),
                    rule_result=failure.rule_result if failure else co_order_rule_result,
                )
            )
        return tuple(exception_orders)

    def _line_rule_failures(self, order: PipelineOrder) -> tuple[PipelineLineRuleFailure, ...]:
        """Finds SKU lines that fail rules independently from their co-order lines."""

        failures: list[PipelineLineRuleFailure] = []
        seen_skus: set[str] = set()
        for order_line in order.order_lines:
            sku_code = order_line.sku_code.strip()
            if not sku_code or sku_code in seen_skus:
                continue
            seen_skus.add(sku_code)
            line_context = replace(order.rule_context, sku_codes=(sku_code,))
            line_result = self.rule_engine.evaluate(line_context, log_hits=False)
            if line_result.is_error:
                failures.append(
                    PipelineLineRuleFailure(
                        sku_code=sku_code,
                        rule_result=line_result.final_result,
                    )
                )
        return tuple(failures)
    # === MODIFIED END ===

    def _deliver_batches(
        self,
        task_context: TaskContext,
        batches: tuple[GroupOrderBatch, ...],
    ) -> tuple[tuple[PipelineBatchDelivery, ...], tuple[PipelineBatchFailure, ...]]:
        deliveries: list[PipelineBatchDelivery] = []
        # === MODIFIED START ===
        # 原因：需要支持多个厂家群推送时的部分失败状态，逐批记录失败并继续后续批次。
        # 影响范围：Pipeline 推送阶段。
        failures: list[PipelineBatchFailure] = []
        # === MODIFIED END ===
        for batch in batches:
            # === MODIFIED START ===
            # 原因：单个批次生成文件或消息推送失败时，不能中断其它批次的推送尝试。
            # 影响范围：Pipeline 部分推送状态判定。
            generated_file: GeneratedFile | None = None
            try:
                generated_file = self.file_generator.generate(batch)
                self._log_info(
                    task_context.trace_id,
                    "pipeline_file_generated",
                    {
                        "group_name": batch.group_name,
                        "file_path": str(generated_file.file_path),
                        "row_count": generated_file.row_count,
                    },
                )

                # === MODIFIED START ===
                # 原因：文件生成后自动上传到公网文件服务器，供群消息发送使用。
                # 影响范围：Pipeline 推送阶段、MessagePayload.file_url。
                file_url: str | None = None
                if self.upload_file is not None:
                    try:
                        file_url = self.upload_file(generated_file.file_path)
                        self._log_info(
                            task_context.trace_id,
                            "pipeline_file_uploaded",
                            {"group_name": batch.group_name, "file_url": file_url},
                        )
                    except Exception as exc:
                        reason = _failure_reason(exc)
                        self._log_error(
                            task_context.trace_id,
                            "pipeline_file_upload_failed",
                            {
                                "group_name": batch.group_name,
                                "file_path": str(generated_file.file_path),
                                "reason": reason,
                            },
                        )
                        raise  # upload failure prevents pushing
                else:
                    file_url = (
                        build_download_url(
                            base_url=self.download_base_url,
                            filename=generated_file.file_path.name,
                            secret_key=self.download_secret_key,
                        )
                        if self.download_base_url and self.download_secret_key
                        else None
                    )
                # === MODIFIED END ===

                # === MODIFIED START ===
                # 原因：user_id 改为推送时惰性解析，避免构建阶段串行调用 API 卡死。
                # 影响范围：MessagePayload.user_id。
                user_id = batch.user_id
                if not user_id and batch.owner_mobile and self.user_resolver is not None:
                    try:
                        user_id = self.user_resolver(batch.owner_mobile)
                    except Exception:
                        user_id = batch.owner_mobile
                # === MODIFIED END ===

                message_result = self.message_sender.send_file(
                    MessagePayload(
                        trace_id=task_context.trace_id,
                        group_name=batch.group_name,
                        owner_mobile=batch.owner_mobile,
                        user_id=user_id,
                        file_path=generated_file.file_path,
                        # === MODIFIED START ===
                        # 原因：文件直推或上传后使用对应 file_url。
                        # 影响范围：Pipeline 推送阶段、MessagePayload.file_url。
                        file_url=file_url,
                        # === MODIFIED END ===
                    )
                )
                self._log_info(
                    task_context.trace_id,
                    "pipeline_message_sent",
                    {
                        "group_name": batch.group_name,
                        "tracking_id": message_result.tracking_id,
                    },
                )
                deliveries.append(
                    PipelineBatchDelivery(
                        batch=batch,
                        generated_file=generated_file,
                        message_result=message_result,
                    )
                )
            except Exception as exc:
                reason = _failure_reason(exc)
                failures.append(
                    PipelineBatchFailure(
                        batch=batch,
                        group_name=batch.group_name,
                        file_path=str(generated_file.file_path) if generated_file else "",
                        reason=reason,
                    )
                )
                self._log_error(
                    task_context.trace_id,
                    "pipeline_batch_delivery_failed",
                    {
                        "group_name": batch.group_name,
                        "file_path": str(generated_file.file_path) if generated_file else "",
                        "reason": reason,
                    },
                )
            # === MODIFIED END ===

        return tuple(deliveries), tuple(failures)

    def _submit_kingdee(
        self,
        task_context: TaskContext,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> str | None:
        if not deliveries:
            self._log_info(
                task_context.trace_id,
                "pipeline_kingdee_skipped",
                {"reason": "no_deliveries"},
            )
            return None

        tracking_id = self.kingdee_service.submit_purchase_request(
            task_context=task_context,
            deliveries=deliveries,
        )
        self._log_info(
            task_context.trace_id,
            "pipeline_kingdee_submitted",
            {"tracking_id": tracking_id},
        )
        return tracking_id

    def _log_info(self, trace_id: str, event: str, payload: dict[str, object]) -> None:
        safe_payload = {"trace_id": trace_id, **payload}
        self.log_info(event, safe_payload)

    def _log_error(self, trace_id: str, event: str, payload: dict[str, object]) -> None:
        safe_payload = {"trace_id": trace_id, **payload}
        self.log_error(event, safe_payload)

    # === MODIFIED START ===
    # 原因：异常订单模型属于 domain，pipeline 只做订单行到异常来源字段的适配。
    # 影响范围：异常订单明细生成。
    @staticmethod
    def _exception_source_from_order_line(order_line: OrderLineForSplit) -> ExceptionOrderSource:
        """Converts one order line into exception order source fields."""

        return ExceptionOrderSource(
            order_no=order_line.order_no,
            sku_code=order_line.sku_code,
            delivery_order_no=order_line.delivery_order_no,
            goods_summary=order_line.goods_summary,
            # === MODIFIED START ===
            # 原因：抓单结果增加仓库字段，异常订单来源需要同步带出。
            # 影响范围：异常订单生成。
            warehouse_code=order_line.warehouse_code,
            warehouse_name=order_line.warehouse_name,
            # === MODIFIED END ===
            quantity=order_line.quantity,
            receiver_name=order_line.receiver_name,
            address=order_line.address,
            phone=order_line.phone,
            logistics_company=order_line.logistics_company,
            logistics_no=order_line.logistics_no,
            # === MODIFIED START ===
            # 原因：从订单行透传推送群和供应商信息到异常订单明细。
            # 影响范围：异常订单生成。
            group_name=order_line.group_name,
            owner_mobile=order_line.owner_mobile,
            supplier_name=order_line.supplier_name,
            # === MODIFIED END ===
        )

    # === MODIFIED START ===
    # 原因：推送群失败属于任务执行异常，需要按失败批次生成可下载异常订单明细。
    # 影响范围：异常订单生成与任务异常统计。
    @classmethod
    def _exception_orders_for_batch_failures(
        cls,
        failures: tuple[PipelineBatchFailure, ...],
    ) -> tuple[ExceptionOrder, ...]:
        """Builds exception order details for failed group push batches."""

        exception_orders: list[ExceptionOrder] = []
        for failure in failures:
            reason = f"推送群失败：{failure.group_name}；{failure.reason}"[:500]
            rule_result = RuleResult(
                decision=RuleDecision.ERROR,
                rule_name="MessagePush",
                reason=reason,
                message=reason,
            )
            exception_orders.extend(
                ExceptionOrder.from_rule_result(
                    source=cls._exception_source_from_order_line(order_line),
                    rule_result=rule_result,
                )
                for order_line in failure.batch.order_lines
            )
        return tuple(exception_orders)
    # === MODIFIED END ===

    @staticmethod
    def _noop_log(event: str, payload: dict[str, object]) -> None:
        _ = (event, payload)


# === MODIFIED START ===
# 原因：连坐异常原因需要把真正失败的 SKU、规则和原因压缩成人可读摘要。
# 影响范围：异常订单 reason 字段。
def _line_failure_summary(failures: tuple[PipelineLineRuleFailure, ...]) -> str:
    """Builds a compact human-readable summary of root SKU rule failures."""

    parts: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for failure in failures:
        reason = failure.rule_result.reason or failure.rule_result.rule_name
        key = (failure.sku_code, failure.rule_result.rule_name, reason)
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"{failure.sku_code}（{reason}）")
    return "；".join(parts)[:460]
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：失败原因需要简洁可持久化，避免把敏感或超长异常直接暴露给接口。
# 影响范围：PipelineRunResult.failure_reason。
def _failure_reason(exc: Exception) -> str:
    """Builds a concise failure reason from an exception."""

    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}: {message}"[:500]


# === MODIFIED START ===
# 原因：多个推送批次失败时，需要形成适合任务详情展示的简明失败摘要。
# 影响范围：PipelineRunResult.failure_reason。
def _batch_failure_reason(failures: tuple[PipelineBatchFailure, ...]) -> str:
    """Builds a concise failure reason for failed push batches."""

    failed_groups = ", ".join(failure.group_name for failure in failures[:5])
    suffix = ""
    if len(failures) > 5:
        suffix = f" 等{len(failures)}个批次"
    first_reason = failures[0].reason if failures else "unknown failure"
    return f"推送批次失败：{failed_groups}{suffix}；首个失败原因：{first_reason}"[:500]
# === MODIFIED END ===
# === MODIFIED END ===
