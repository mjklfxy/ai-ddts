from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.file_generator import ExcelFileGenerator
from application.order_splitter import OrderSplitter
from application.pipeline import Pipeline, PipelineBatchDelivery, PipelineOrder
from application.task_service import TaskService
from domain.enums.status import KingdeeStatus, PushStatus
from domain.rule_engine import RuleEngine
from domain.rules.base import RuleContext
from domain.rules.group_rule import GroupRule
from domain.rules.sku_rule import SkuServiceRule
from domain.rules.warehouse_rule import WarehouseRule
from domain.sku_group_info import SkuGroupInfo
from domain.supplier import MissingSupplierError
from infrastructure.message_adapter import MessagePayload, MessageSendResult
from tests.test_order_splitter import make_order_line


class RecordingMessageSender:
    """Records message payloads sent by the pipeline."""

    def __init__(self) -> None:
        self.payloads: list[MessagePayload] = []

    def send_file(self, payload: MessagePayload) -> MessageSendResult:
        self.payloads.append(payload)
        return MessageSendResult(
            trace_id=payload.trace_id,
            group_name=payload.group_name,
            tracking_id=f"MSG-{payload.group_name}",
            attempts=1,
        )


class RecordingKingdeeService:
    """Records Kingdee submissions made by the pipeline."""

    def __init__(self) -> None:
        self.deliveries: tuple[PipelineBatchDelivery, ...] | None = None

    def submit_purchase_request(
        self,
        task_context,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> str:
        _ = task_context
        self.deliveries = deliveries
        return "KINGDEE-001"


# === MODIFIED START ===
# 原因：任务状态持久化需要覆盖消息推送失败和金蝶提交失败。
# 影响范围：pipeline 状态输出测试。
class FailingMessageSender:
    """Always fails message sending for status tests."""

    def send_file(self, payload: MessagePayload) -> MessageSendResult:
        """Raises a deterministic message failure."""

        _ = payload
        raise RuntimeError("message gateway down")


# === MODIFIED START ===
# 原因：推送状态新增“部分推送”，需要覆盖部分厂家群成功、部分厂家群失败的场景。
# 影响范围：Pipeline 推送状态测试。
class PartiallyFailingMessageSender:
    """Fails selected group messages while allowing other groups to succeed."""

    def __init__(self, failed_group_ids: set[str]) -> None:
        self.failed_group_ids = failed_group_ids
        self.payloads: list[MessagePayload] = []

    def send_file(self, payload: MessagePayload) -> MessageSendResult:
        """Sends successful groups and raises for configured failed groups."""

        self.payloads.append(payload)
        if payload.group_name in self.failed_group_ids:
            raise RuntimeError(f"group {payload.group_name} gateway down")
        return MessageSendResult(
            trace_id=payload.trace_id,
            group_name=payload.group_name,
            tracking_id=f"MSG-{payload.group_name}",
            attempts=1,
        )
# === MODIFIED END ===


class FailingKingdeeService:
    """Always fails Kingdee submission for status tests."""

    def submit_purchase_request(
        self,
        task_context,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> str:
        """Raises a deterministic Kingdee failure."""

        _ = (task_context, deliveries)
        raise RuntimeError("kingdee gateway down")


class MissingSupplierKingdeeService:
    """Fails Kingdee submission with missing supplier mapping after push."""

    def __init__(self) -> None:
        self.deliveries: tuple[PipelineBatchDelivery, ...] | None = None

    def submit_purchase_request(
        self,
        task_context,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> str:
        """Raises a deterministic missing supplier error."""

        _ = task_context
        self.deliveries = deliveries
        raise MissingSupplierError(("SKU-001",))
# === MODIFIED END ===


class PipelineTests(TestCase):
    """Tests pipeline stage orchestration without embedding business rules."""

    def test_run_orchestrates_pass_ignore_error_and_deliveries(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        task = make_task()
        message_sender = RecordingMessageSender()
        kingdee_service = RecordingKingdeeService()
        pipeline = build_pipeline(
            log_info=lambda event, payload: logs.append((event, payload)),
            message_sender=message_sender,
            kingdee_service=kingdee_service,
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS", sku_code="SKU-001"),),
                ),
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-IGNORE",
                        trace_id=task.trace_id,
                        warehouse_code="WH-IGNORE",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-IGNORE", sku_code="SKU-001"),),
                ),
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-ERROR",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-002",),
                    ),
                    order_lines=(make_order_line(order_no="SO-ERROR", sku_code="SKU-002"),),
                ),
            ],
        )

        self.assertEqual([item.order_no for item in result.passed_orders], ["SO-PASS"])
        self.assertEqual([item.order_no for item in result.ignored_orders], ["SO-IGNORE"])
        self.assertEqual([item.order_no for item in result.error_orders], ["SO-ERROR"])
        # === MODIFIED START ===
        # 原因：pipeline 现在会把规则失败订单转换成异常订单明细；SKU 排除不再产生异常。
        # 影响范围：pipeline 编排结果测试。
        self.assertEqual([item.order_no for item in result.exception_orders], ["SO-ERROR"])
        self.assertEqual(result.exception_orders[0].sku_code, "SKU-002")
        self.assertEqual(result.exception_orders[0].rule_name, "GroupRule")
        # === MODIFIED END ===
        self.assertEqual(len(result.deliveries), 1)
        self.assertEqual(result.deliveries[0].batch.group_name, "GROUP-A")
        self.assertEqual(result.deliveries[0].message_result.tracking_id, "MSG-GROUP-A")
        self.assertEqual(result.kingdee_tracking_id, "KINGDEE-001")
        # === MODIFIED START ===
        # 原因：成功链路需要输出可持久化状态。
        # 影响范围：pipeline 编排结果测试。
        self.assertEqual(result.push_status, PushStatus.SUCCESS)
        self.assertEqual(result.kingdee_status, KingdeeStatus.SUCCESS)
        self.assertIsNone(result.failure_stage)
        self.assertIsNone(result.failure_reason)
        # === MODIFIED END ===
        self.assertEqual(len(message_sender.payloads), 1)
        self.assertIsNotNone(kingdee_service.deliveries)
        self.assertTrue(all(payload["trace_id"] == task.trace_id for _, payload in logs))
        self.assertIn("pipeline_finished", [event for event, _ in logs])

    # === MODIFIED START ===
    # 原因：整单异常会把同订单正常 SKU 一并带入异常明细，连坐行需要说明真正异常的 SKU 和原因。
    # 影响范围：Pipeline 规则异常明细原因。
    def test_co_order_exception_reason_points_to_root_sku(self) -> None:
        task = make_task()
        pipeline = build_pipeline(
            log_info=lambda event, payload: None,
            message_sender=RecordingMessageSender(),
            kingdee_service=RecordingKingdeeService(),
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-MULTI",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001", "SKU-002"),
                    ),
                    order_lines=(
                        make_order_line(order_no="SO-MULTI", sku_code="SKU-001"),
                        make_order_line(order_no="SO-MULTI", sku_code="SKU-002"),
                    ),
                ),
            ],
        )

        reasons = {item.sku_code: item.reason for item in result.exception_orders}

        self.assertEqual(reasons["SKU-002"], "\u672a\u914d\u7f6e\u63a8\u9001\u7fa4")
        self.assertIn("\u540c\u8ba2\u5355\u5176\u4ed6SKU\u5f02\u5e38", reasons["SKU-001"])
        self.assertIn("SKU-002", reasons["SKU-001"])
        self.assertIn("\u672a\u914d\u7f6e\u63a8\u9001\u7fa4", reasons["SKU-001"])
    # === MODIFIED END ===

    def test_no_passed_orders_skip_delivery_and_kingdee(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        task = make_task()
        message_sender = RecordingMessageSender()
        kingdee_service = RecordingKingdeeService()
        pipeline = build_pipeline(
            log_info=lambda event, payload: logs.append((event, payload)),
            message_sender=message_sender,
            kingdee_service=kingdee_service,
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-IGNORE",
                        trace_id=task.trace_id,
                        warehouse_code="WH-IGNORE",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-IGNORE", sku_code="SKU-001"),),
                )
            ],
        )

        self.assertEqual(result.deliveries, ())
        self.assertEqual(result.exception_orders, ())
        self.assertIsNone(result.kingdee_tracking_id)
        # === MODIFIED START ===
        # 原因：无可推送订单时保留待推送/金蝶待提交状态。
        # 影响范围：pipeline 状态输出。
        self.assertEqual(result.push_status, PushStatus.PENDING)
        self.assertEqual(result.kingdee_status, KingdeeStatus.PENDING)
        # === MODIFIED END ===
        self.assertEqual(message_sender.payloads, [])
        self.assertIsNone(kingdee_service.deliveries)
        self.assertIn("pipeline_kingdee_skipped", [event for event, _ in logs])

    # === MODIFIED START ===
    # 原因：消息推送失败必须落任务状态，而不是中断为未记录任务。
    # 影响范围：pipeline 状态输出。
    def test_message_failure_returns_failed_push_status(self) -> None:
        task = make_task()
        pipeline = build_pipeline(
            log_info=lambda event, payload: None,
            message_sender=FailingMessageSender(),
            kingdee_service=RecordingKingdeeService(),
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS", sku_code="SKU-001"),),
                )
            ],
        )

        self.assertEqual(result.push_status, PushStatus.FAILED)
        self.assertEqual(result.kingdee_status, KingdeeStatus.PENDING)
        self.assertEqual(result.failure_stage, "message_push")
        self.assertIn("RuntimeError", result.failure_reason)
        self.assertIsNone(result.kingdee_tracking_id)
        # === MODIFIED START ===
        # 原因：推送群失败需要计入异常订单明细。
        # 影响范围：Pipeline 消息推送失败输出。
        self.assertEqual([item.order_no for item in result.exception_orders], ["SO-PASS"])
        self.assertEqual(result.exception_orders[0].rule_name, "MessagePush")
        self.assertIn("推送群失败", result.exception_orders[0].reason)
        # === MODIFIED END ===

    def test_partial_message_failure_returns_partial_push_status(self) -> None:
        task = make_task()
        message_sender = PartiallyFailingMessageSender(failed_group_ids={"GROUP-B"})
        kingdee_service = RecordingKingdeeService()
        pipeline = build_pipeline(
            log_info=lambda event, payload: None,
            message_sender=message_sender,
            kingdee_service=kingdee_service,
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS-A",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS-A", sku_code="SKU-001"),),
                ),
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS-B",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-003",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS-B", sku_code="SKU-003"),),
                ),
            ],
        )

        self.assertEqual(result.push_status, PushStatus.PARTIAL)
        self.assertEqual(result.kingdee_status, KingdeeStatus.SUCCESS)
        self.assertEqual(result.failure_stage, "message_push")
        self.assertIn("GROUP-B", result.failure_reason)
        self.assertEqual([delivery.batch.group_name for delivery in result.deliveries], ["GROUP-A"])
        self.assertEqual([payload.group_name for payload in message_sender.payloads], ["GROUP-A", "GROUP-B"])
        self.assertIsNotNone(kingdee_service.deliveries)
        self.assertEqual([delivery.batch.group_name for delivery in kingdee_service.deliveries], ["GROUP-A"])
        # === MODIFIED START ===
        # 原因：部分推送失败时，失败批次订单需要进入异常明细。
        # 影响范围：Pipeline 部分推送异常输出。
        self.assertEqual([item.order_no for item in result.exception_orders], ["SO-PASS-B"])
        self.assertEqual(result.exception_orders[0].rule_name, "MessagePush")
        self.assertIn("GROUP-B", result.exception_orders[0].reason)
        # === MODIFIED END ===

    def test_kingdee_failure_returns_failed_kingdee_status(self) -> None:
        task = make_task()
        pipeline = build_pipeline(
            log_info=lambda event, payload: None,
            message_sender=RecordingMessageSender(),
            kingdee_service=FailingKingdeeService(),
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS", sku_code="SKU-001"),),
                )
            ],
        )

        self.assertEqual(result.push_status, PushStatus.SUCCESS)
        self.assertEqual(result.kingdee_status, KingdeeStatus.FAILED)
        self.assertEqual(result.failure_stage, "kingdee_submit")
        self.assertIn("RuntimeError", result.failure_reason)
        self.assertIsNone(result.kingdee_tracking_id)

    # === MODIFIED START ===
    # 原因：金蝶推送可关闭，关闭时不应调用金蝶服务。
    # 影响范围：Pipeline 金蝶阶段编排。
    def test_disabled_kingdee_skips_purchase_request(self) -> None:
        task = make_task()
        kingdee_service = RecordingKingdeeService()
        pipeline = build_pipeline(
            log_info=lambda event, payload: None,
            message_sender=RecordingMessageSender(),
            kingdee_service=kingdee_service,
            kingdee_enabled=False,
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS", sku_code="SKU-001"),),
                )
            ],
        )

        self.assertEqual(result.push_status, PushStatus.SUCCESS)
        self.assertEqual(result.kingdee_status, KingdeeStatus.DISABLED)
        self.assertIsNone(result.kingdee_tracking_id)
        self.assertIsNone(kingdee_service.deliveries)
    # === MODIFIED END ===

    def test_missing_supplier_after_push_returns_kingdee_failure_without_exception_detail(self) -> None:
        task = make_task()
        kingdee_service = MissingSupplierKingdeeService()
        pipeline = build_pipeline(
            log_info=lambda event, payload: None,
            message_sender=RecordingMessageSender(),
            kingdee_service=kingdee_service,
        )

        result = pipeline.run(
            task_context=task,
            orders=[
                PipelineOrder(
                    rule_context=RuleContext(
                        order_no="SO-PASS",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_codes=("SKU-001",),
                    ),
                    order_lines=(make_order_line(order_no="SO-PASS", sku_code="SKU-001"),),
                )
            ],
        )

        self.assertEqual([item.order_no for item in result.passed_orders], ["SO-PASS"])
        self.assertEqual(len(result.deliveries), 1)
        self.assertIsNotNone(kingdee_service.deliveries)
        self.assertEqual(result.push_status, PushStatus.SUCCESS)
        self.assertEqual(result.kingdee_status, KingdeeStatus.FAILED)
        self.assertEqual(result.failure_stage, "kingdee_submit")
        # === MODIFIED START ===
        # 原因：SKU-供应商对照缺失不计入异常订单，只影响金蝶提交状态。
        # 影响范围：Pipeline 金蝶失败异常输出。
        self.assertEqual(result.exception_orders, ())
        # === MODIFIED END ===
    # === MODIFIED END ===


def make_task():
    """Builds a deterministic task context for pipeline tests."""

    return TaskService(
        trace_id_generator=lambda: "TRACE-001",
        clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
    ).create_task(
        task_name="daily-direct-order",
        window_start=datetime(2026, 4, 30, 8, 0, 0),
        window_end=datetime(2026, 4, 30, 12, 0, 0),
    )


def build_pipeline(log_info, message_sender, kingdee_service, kingdee_enabled: bool = True) -> Pipeline:
    """Builds a pipeline with deterministic rules and output paths."""

    sku_group_map = {"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""), "SKU-003": SkuGroupInfo(group_name="GROUP-B", owner_mobile="")}
    return Pipeline(
        rule_engine=RuleEngine(
            rules=[
                WarehouseRule(excluded_warehouses={"WH-IGNORE"}),
                # === MODIFIED START ===
                # 原因：SKU 规则改为排除黑名单，测试默认不排除 SKU。
                # 影响范围：pipeline 测试规则构建。
                SkuServiceRule(excluded_skus=set()),
                # === MODIFIED END ===
                GroupRule(sku_group_map=sku_group_map),
            ],
            log_info=log_info,
        ),
        order_splitter=OrderSplitter(sku_group_map=sku_group_map),
        file_generator=ExcelFileGenerator(
            output_dir=Path("tmp") / "test_pipeline",
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
        ),
        message_sender=message_sender,
        kingdee_service=kingdee_service,
        kingdee_enabled=kingdee_enabled,
        log_info=log_info,
    )
