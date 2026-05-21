from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext
from domain.rules.order_prefix_rule import OrderPrefixRule


class OrderPrefixRuleTests(TestCase):
    """Tests order prefix filtering as IGNORE for non-matching prefixes."""

    def test_inherits_order_rule(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=("JY",))

        self.assertIsInstance(rule, OrderRule)

    def test_matching_prefix_returns_pass(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=("JY",))

        result = rule.evaluate(RuleContext(order_no="JY202605150001"))

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
        self.assertEqual(result.rule_name, "OrderPrefixRule")

    def test_non_matching_prefix_returns_ignore(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=("JY",))

        result = rule.evaluate(RuleContext(order_no="CK202605150027"))

        self.assertEqual(result.decision, RuleDecision.IGNORE)
        self.assertTrue(result.is_ignore)
        self.assertEqual(result.reason, "订单号前缀不在白名单")
        self.assertEqual(result.rule_name, "OrderPrefixRule")

    def test_multiple_prefixes_matching_second_returns_pass(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=("JY", "CK", "SO"))

        result = rule.evaluate(RuleContext(order_no="CK202605150027"))

        self.assertEqual(result.decision, RuleDecision.PASS)

    def test_multiple_prefixes_none_match_returns_ignore(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=("JY", "SO"))

        result = rule.evaluate(RuleContext(order_no="XX202605150001"))

        self.assertEqual(result.decision, RuleDecision.IGNORE)

    def test_disabled_module_returns_pass_for_non_matching(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=("JY",), enabled=False)

        result = rule.evaluate(RuleContext(order_no="CK202605150027"))

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)

    def test_empty_allowed_prefixes_returns_pass(self) -> None:
        rule = OrderPrefixRule(allowed_prefixes=())

        result = rule.evaluate(RuleContext(order_no="CK202605150027"))

        self.assertEqual(result.decision, RuleDecision.PASS)
