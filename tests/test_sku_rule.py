from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext
from domain.rules.sku_rule import SkuServiceRule


class SkuServiceRuleTests(TestCase):
    """Tests SKU exclusion filtering as whole-order ignores."""

    def test_inherits_order_rule(self) -> None:
        rule = SkuServiceRule(excluded_skus={"SKU-001"})

        self.assertIsInstance(rule, OrderRule)

    # === MODIFIED START ===
    # 原因：SKU 规则实际是排除逻辑，不是启用白名单。
    # 影响范围：SkuServiceRule 单元测试。
    def test_non_excluded_skus_return_pass(self) -> None:
        rule = SkuServiceRule(excluded_skus={"SKU-003"})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001", "SKU-002"),
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)

    def test_excluded_sku_returns_ignore(self) -> None:
        rule = SkuServiceRule(excluded_skus={"SKU-002"})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-002",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.IGNORE)
        self.assertTrue(result.is_ignore)
        self.assertEqual(result.reason, "SKU排除")
        self.assertEqual(result.rule_name, "SkuServiceRule")

    def test_any_excluded_sku_returns_whole_order_ignore(self) -> None:
        rule = SkuServiceRule(excluded_skus={"SKU-002"})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001", "SKU-002"),
            )
        )

        self.assertEqual(result.decision, RuleDecision.IGNORE)
        self.assertIn("SKU-002", result.message)

    def test_disabled_module_returns_pass_even_when_sku_is_listed(self) -> None:
        rule = SkuServiceRule(excluded_skus={"SKU-002"}, enabled=False)

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-002",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
    # === MODIFIED END ===
