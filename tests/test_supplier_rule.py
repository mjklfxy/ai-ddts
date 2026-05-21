from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext
from domain.rules.supplier_rule import SupplierRule
from domain.supplier import SupplierInfo


class SupplierRuleTests(TestCase):
    """Tests SKU to supplier mapping rule checks."""

    def test_inherits_order_rule(self) -> None:
        rule = SupplierRule(sku_supplier_map={})

        self.assertIsInstance(rule, OrderRule)

    def test_all_skus_with_supplier_mapping_return_pass(self) -> None:
        rule = SupplierRule(sku_supplier_map={"SKU-001": make_supplier("SKU-001")})

        result = rule.evaluate(RuleContext(order_no="SO-001", sku_codes=("SKU-001",)))

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)

    def test_missing_supplier_mapping_returns_pass(self) -> None:
        rule = SupplierRule(sku_supplier_map={"SKU-001": make_supplier("SKU-001")})

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001", "SKU-002"),
            )
        )

        # === MODIFIED START ===
        # 原因：SKU-供应商对照缺失不属于订单异常规则。
        # 影响范围：SupplierRule 评估口径。
        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
        self.assertEqual(result.rule_name, "SupplierRule")
        # === MODIFIED END ===


def make_supplier(sku_code: str) -> SupplierInfo:
    """Builds one supplier mapping for rule tests."""

    return SupplierInfo(
        sku_code=sku_code,
        supplier_name=f"Supplier {sku_code}",
    )
