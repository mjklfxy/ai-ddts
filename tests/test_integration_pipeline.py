import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.file_generator import CsvFileGenerator
from application.order_splitter import OrderSplitter
from application.pipeline import Pipeline, PipelineBatchDelivery, PipelineOrder
from application.task_service import TaskService
from domain.enums.rule import RuleDecision
from domain.enums.status import KingdeeStatus, PushStatus
from domain.rule_engine import RuleEngine
from domain.rules.base import RuleContext
from domain.rules.group_rule import GroupRule
from domain.rules.region_rule import RegionRule, RestrictedRegion
from domain.rules.sku_rule import SkuServiceRule
from domain.rules.warehouse_rule import WarehouseRule
from domain.sku_group_info import SkuGroupInfo
from infrastructure.message_adapter import MessageAdapter
from shared.logging.logger import log_error, log_info
from tests.test_order_splitter import make_order_line


class RecordingKingdeeService:
    """Records purchase request submissions during integration tests."""

    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[PipelineBatchDelivery, ...]]] = []

    def submit_purchase_request(
        self,
        task_context,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> str:
        self.submissions.append((task_context, deliveries))
        return "KINGDEE-TRACE-001"


class RecordingLogHandler(logging.Handler):
    """Collects structured log messages emitted by shared logging."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, object]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(json.loads(record.getMessage()))


class PipelineIntegrationTests(TestCase):
    """Tests the full task pipeline across domain, application, infrastructure, and shared layers."""

    def test_pipeline_runs_pass_ignore_error_retry_and_kingdee_submission(self) -> None:
        handler = attach_log_handler()
        output_dir = Path("tmp") / "test_integration_pipeline"
        send_attempts: list[str] = []
        kingdee_service = RecordingKingdeeService()
        try:
            task = TaskService(
                trace_id_generator=lambda: "TRACE-001",
                clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
            ).create_task(
                task_name="daily-direct-order",
                window_start=datetime(2026, 4, 30, 8, 0, 0),
                window_end=datetime(2026, 4, 30, 12, 0, 0),
            )
            sku_group_map = {
                "SKU-PASS": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""),
                "SKU-REGION": SkuGroupInfo(group_name="GROUP-B", owner_mobile=""),
            }
            pipeline = Pipeline(
                rule_engine=RuleEngine(
                    rules=[
                        WarehouseRule(excluded_warehouses={"WH-IGNORE"}),
                        # === MODIFIED START ===
                        # 原因：SKU 规则是排除逻辑；命中排除 SKU 应忽略订单。
                        # 影响范围：pipeline 集成测试规则链。
                        SkuServiceRule(
                            excluded_skus={"SKU-EXCLUDED"}
                        ),
                        # === MODIFIED END ===
                        RegionRule(
                            restricted_regions=[
                                RestrictedRegion(
                                    sku_code="SKU-REGION",
                                    province="浙江省",
                                    city="杭州市",
                                )
                            ]
                        ),
                        GroupRule(sku_group_map=sku_group_map),
                    ],
                    log_info=log_info,
                ),
                order_splitter=OrderSplitter(sku_group_map=sku_group_map),
                file_generator=CsvFileGenerator(
                    output_dir=output_dir,
                    clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
                ),
                message_sender=MessageAdapter(
                    sender=lambda payload: flaky_sender(payload.group_name, send_attempts),
                    max_attempts=2,
                    log_info=log_info,
                    log_error=log_error,
                ),
                kingdee_service=kingdee_service,
                log_info=log_info,
                log_error=log_error,
            )

            result = pipeline.run(
                task_context=task,
                orders=[
                    make_pipeline_order(
                        order_no="SO-PASS",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_code="SKU-PASS",
                        province="广东省",
                        city="深圳市",
                    ),
                    make_pipeline_order(
                        order_no="SO-IGNORE",
                        trace_id=task.trace_id,
                        warehouse_code="WH-IGNORE",
                        sku_code="SKU-PASS",
                        province="广东省",
                        city="深圳市",
                    ),
                    make_pipeline_order(
                        order_no="SO-SKU",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_code="SKU-EXCLUDED",
                        province="广东省",
                        city="深圳市",
                    ),
                    make_pipeline_order(
                        order_no="SO-REGION",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_code="SKU-REGION",
                        province="浙江省",
                        city="杭州市",
                    ),
                    make_pipeline_order(
                        order_no="SO-GROUP",
                        trace_id=task.trace_id,
                        warehouse_code="WH-OK",
                        sku_code="SKU-NO-GROUP",
                        province="广东省",
                        city="深圳市",
                    ),
                ],
            )
        finally:
            detach_log_handler(handler)

        self.assertEqual([item.order_no for item in result.passed_orders], ["SO-PASS"])
        self.assertEqual([item.order_no for item in result.ignored_orders], ["SO-IGNORE", "SO-SKU"])
        self.assertEqual([item.order_no for item in result.error_orders], ["SO-REGION", "SO-GROUP"])
        self.assertEqual(
            [item.engine_result.final_result.decision for item in result.error_orders],
            [RuleDecision.ERROR, RuleDecision.ERROR],
        )
        self.assertEqual(
            [item.engine_result.final_result.reason for item in result.error_orders],
            ["命中限发区域", "未配置推送群"],
        )
        # === MODIFIED START ===
        # 原因：集成链路需要验证异常订单明细随 pipeline 结果输出。
        # 影响范围：pipeline 集成测试。
        self.assertEqual(
            [item.order_no for item in result.exception_orders],
            ["SO-REGION", "SO-GROUP"],
        )
        self.assertEqual(
            [item.rule_name for item in result.exception_orders],
            ["RegionRule", "GroupRule"],
        )
        # === MODIFIED END ===
        self.assertEqual(len(result.deliveries), 1)
        self.assertEqual(result.deliveries[0].batch.group_name, "GROUP-A")
        self.assertEqual(result.deliveries[0].message_result.attempts, 2)
        self.assertEqual(result.kingdee_tracking_id, "KINGDEE-TRACE-001")
        # === MODIFIED START ===
        # 原因：集成链路需要验证任务状态输出可供持久化。
        # 影响范围：pipeline 集成测试。
        self.assertEqual(result.push_status, PushStatus.SUCCESS)
        self.assertEqual(result.kingdee_status, KingdeeStatus.SUCCESS)
        self.assertIsNone(result.failure_stage)
        # === MODIFIED END ===
        self.assertEqual(len(kingdee_service.submissions), 1)
        self.assertEqual(send_attempts, ["GROUP-A", "GROUP-A"])

        rows = read_csv(result.deliveries[0].generated_file.file_path)
        self.assertEqual(rows[1][0], "SO-PASS")
        self.assertEqual(rows[1][2], "Goods SKU-PASS")

        events = [message["event"] for message in handler.messages]
        self.assertIn("rule_hit", events)
        self.assertIn("message_send_failed", events)
        self.assertIn("message_send_success", events)
        self.assertIn("pipeline_kingdee_submitted", events)
        self.assertTrue(
            all(message["payload"]["trace_id"] == "TRACE-001" for message in handler.messages)
        )


def make_pipeline_order(
    order_no: str,
    trace_id: str,
    warehouse_code: str,
    sku_code: str,
    province: str,
    city: str,
) -> PipelineOrder:
    """Builds one adapted order for the integration pipeline."""

    return PipelineOrder(
        rule_context=RuleContext(
            order_no=order_no,
            trace_id=trace_id,
            warehouse_code=warehouse_code,
            sku_codes=(sku_code,),
            receiver_province=province,
            receiver_city=city,
        ),
        order_lines=(make_order_line(order_no=order_no, sku_code=sku_code),),
    )


def flaky_sender(group_name: str, send_attempts: list[str]) -> str:
    """Fails once and then returns a tracking id for retry verification."""

    send_attempts.append(group_name)
    if len(send_attempts) == 1:
        raise RuntimeError("temporary message failure")
    return f"MSG-{group_name}"


def read_csv(file_path: Path) -> list[list[str]]:
    """Reads a generated CSV file."""

    with file_path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.reader(file))


def attach_log_handler() -> RecordingLogHandler:
    """Attaches a structured log recorder to the project logger."""

    logger = logging.getLogger("ai_ddts")
    logger.setLevel(logging.INFO)
    handler = RecordingLogHandler()
    logger.addHandler(handler)
    return handler


def detach_log_handler(handler: RecordingLogHandler) -> None:
    """Detaches the structured log recorder from the project logger."""

    logger = logging.getLogger("ai_ddts")
    logger.removeHandler(handler)
