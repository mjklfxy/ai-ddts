from unittest import TestCase

from domain.enums.exception import ExceptionProcessStatus
from domain.enums.rule import RuleDecision
from domain.exception_order import ExceptionOrder, ExceptionOrderSource
from domain.rules.base import RuleResult


class ExceptionOrderTests(TestCase):
    """Tests exception order details for export and manual processing."""

    def test_from_rule_result_creates_pending_exception_order(self) -> None:
        exception_order = ExceptionOrder.from_rule_result(
            source=make_source(),
            rule_result=RuleResult(
                decision=RuleDecision.ERROR,
                # === MODIFIED START ===
                # 原因：SkuServiceRule 已改为 IGNORE，异常订单示例改用群配置错误。
                # 影响范围：异常订单领域模型测试。
                rule_name="GroupRule",
                reason="未配置推送群",
                # === MODIFIED END ===
            ),
        )

        self.assertIsInstance(exception_order, ExceptionOrder)
        self.assertEqual(exception_order.order_no, "SO-001")
        # === MODIFIED START ===
        # 原因：异常订单导出新增 SKU 字段。
        # 影响范围：异常订单领域模型测试。
        self.assertEqual(exception_order.sku_code, "SKU-001")
        # === MODIFIED END ===
        self.assertEqual(exception_order.delivery_order_no, "DO-001")
        self.assertEqual(exception_order.goods_summary, "货品摘要")
        # === MODIFIED START ===
        # 原因：异常订单需要保留抓单仓库字段。
        # 影响范围：异常订单领域模型测试。
        self.assertEqual(exception_order.warehouse_name, "华东仓")
        # === MODIFIED END ===
        self.assertEqual(exception_order.reason, "未配置推送群")
        self.assertEqual(exception_order.rule_name, "GroupRule")
        self.assertEqual(exception_order.process_status, ExceptionProcessStatus.PENDING)
        self.assertEqual(exception_order.process_status.value, "待处理")

    def test_custom_process_status_is_supported(self) -> None:
        exception_order = ExceptionOrder.from_rule_result(
            source=make_source(),
            rule_result=RuleResult(
                decision=RuleDecision.ERROR,
                rule_name="RegionRule",
                reason="命中限发区域",
            ),
            process_status=ExceptionProcessStatus.PROCESSED,
        )

        self.assertEqual(exception_order.process_status, ExceptionProcessStatus.PROCESSED)
        self.assertEqual(exception_order.process_status.value, "已处理")

    def test_missing_reason_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "reason"):
            ExceptionOrder.from_rule_result(
                source=make_source(),
                rule_result=RuleResult(
                    decision=RuleDecision.ERROR,
                    rule_name="SkuServiceRule",
                    reason=None,
                ),
            )

    def test_missing_rule_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "rule_name"):
            ExceptionOrder.from_rule_result(
                source=make_source(),
                rule_result=RuleResult(
                    decision=RuleDecision.ERROR,
                    rule_name="",
                    reason="未配置推送群",
                ),
            )


def make_source() -> ExceptionOrderSource:
    """Builds source fields for exception order tests."""

    return ExceptionOrderSource(
        order_no="SO-001",
        # === MODIFIED START ===
        # 原因：异常订单来源新增 SKU 字段。
        # 影响范围：异常订单测试数据。
        sku_code="SKU-001",
        # === MODIFIED END ===
        delivery_order_no="DO-001",
        goods_summary="货品摘要",
        # === MODIFIED START ===
        # 原因：异常订单来源新增仓库字段。
        # 影响范围：异常订单测试数据。
        warehouse_code="WH-001",
        warehouse_name="华东仓",
        # === MODIFIED END ===
        quantity=1,
        receiver_name="Receiver",
        address="Address",
        phone="13800000000",
        logistics_company="SF",
        logistics_no="SF001",
    )
