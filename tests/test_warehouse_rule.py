from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext
from domain.rules.warehouse_rule import WarehouseRule


class WarehouseRuleTests(TestCase):
    """Tests warehouse filtering as IGNORE rather than ERROR."""

    def test_inherits_order_rule(self) -> None:
        rule = WarehouseRule(excluded_warehouses={"WH-001"})

        self.assertIsInstance(rule, OrderRule)

    def test_excluded_warehouse_code_returns_ignore(self) -> None:
        rule = WarehouseRule(excluded_warehouses={"WH-001"})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                warehouse_code="WH-001",
                warehouse_name="华东仓",
            )
        )

        self.assertEqual(result.decision, RuleDecision.IGNORE)
        self.assertTrue(result.is_ignore)
        self.assertFalse(result.is_error)
        self.assertEqual(result.reason, "仓库过滤")
        self.assertEqual(result.rule_name, "WarehouseRule")

    def test_excluded_warehouse_name_returns_ignore(self) -> None:
        rule = WarehouseRule(excluded_warehouses={"华东仓"})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                warehouse_code="WH-001",
                warehouse_name="华东仓",
            )
        )

        self.assertEqual(result.decision, RuleDecision.IGNORE)

    def test_non_excluded_warehouse_returns_pass(self) -> None:
        rule = WarehouseRule(excluded_warehouses={"WH-001"})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-002",
                warehouse_code="WH-002",
                warehouse_name="华南仓",
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
        self.assertIsNone(result.reason)

    # === MODIFIED START ===
    # 原因：排除库房模块新增启用开关，关闭时命中库房也不能忽略订单。
    # 影响范围：WarehouseRule 禁用行为。
    def test_disabled_module_returns_pass_even_when_warehouse_matches(self) -> None:
        rule = WarehouseRule(excluded_warehouses={"WH-001"}, enabled=False)

        result = rule.evaluate(
            RuleContext(
                order_no="SO-003",
                warehouse_code="WH-001",
                warehouse_name="华东仓",
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
    # === MODIFIED END ===
