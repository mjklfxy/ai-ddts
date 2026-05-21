from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext
from domain.rules.group_rule import GroupRule
from domain.sku_group_info import SkuGroupInfo


class GroupRuleTests(TestCase):
    """Tests missing SKU push group failures as whole-order errors."""

    def test_inherits_order_rule(self) -> None:
        rule = GroupRule(sku_group_map={"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile="")})

        self.assertIsInstance(rule, OrderRule)

    def test_all_mapped_skus_return_pass(self) -> None:
        rule = GroupRule(
            sku_group_map={
                "SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""),
                "SKU-002": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""),
            }
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001", "SKU-002"),
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)

    def test_missing_group_returns_error(self) -> None:
        rule = GroupRule(sku_group_map={"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile="")})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-002",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)
        self.assertTrue(result.is_error)
        self.assertEqual(result.reason, "未配置推送群")
        self.assertEqual(result.rule_name, "GroupRule")

    def test_any_missing_group_returns_whole_order_error(self) -> None:
        rule = GroupRule(sku_group_map={"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile="")})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001", "SKU-002"),
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)
        self.assertIn("SKU-002", result.message)

    def test_blank_group_is_treated_as_missing(self) -> None:
        rule = GroupRule(sku_group_map={"SKU-001": SkuGroupInfo(group_name=" ", owner_mobile="")})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)

    # === MODIFIED START ===
    # 原因：SKU 群配置模块新增启用开关，关闭时缺群不作为规则异常。
    # 影响范围：GroupRule 禁用行为。
    def test_disabled_module_returns_pass_even_when_group_is_missing(self) -> None:
        rule = GroupRule(sku_group_map={}, enabled=False)

        result = rule.evaluate(
            RuleContext(
                order_no="SO-002",
                sku_codes=("SKU-NO-GROUP",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
    # === MODIFIED END ===
