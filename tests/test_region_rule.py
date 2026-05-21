from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext
from domain.rules.region_rule import RegionRule, RestrictedRegion


class RegionRuleTests(TestCase):
    """Tests restricted region matches as whole-order errors."""

    def test_inherits_order_rule(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(sku_code="SKU-001", province="浙江省"),
            ]
        )

        self.assertIsInstance(rule, OrderRule)

    def test_province_only_match_returns_error(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(sku_code="SKU-001", province="浙江省"),
            ]
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001",),
                receiver_province="浙江省",
                receiver_city="杭州市",
                receiver_district="西湖区",
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)
        self.assertTrue(result.is_error)
        self.assertEqual(result.reason, "命中限发区域")
        self.assertEqual(result.rule_name, "RegionRule")

    def test_province_city_match_returns_error(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(sku_code="SKU-001", province="浙江省", city="杭州市"),
            ]
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001",),
                receiver_province="浙江省",
                receiver_city="杭州市",
                receiver_district="西湖区",
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)

    def test_province_city_district_match_returns_error(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(
                    sku_code="SKU-001",
                    province="浙江省",
                    city="杭州市",
                    district="西湖区",
                ),
            ]
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001",),
                receiver_province="浙江省",
                receiver_city="杭州市",
                receiver_district="西湖区",
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)

    def test_city_mismatch_returns_pass(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(sku_code="SKU-001", province="浙江省", city="杭州市"),
            ]
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001",),
                receiver_province="浙江省",
                receiver_city="宁波市",
                receiver_district="海曙区",
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)

    def test_any_sku_match_returns_whole_order_error(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(sku_code="SKU-002", province="浙江省", city="杭州市"),
            ]
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-001",
                sku_codes=("SKU-001", "SKU-002"),
                receiver_province="浙江省",
                receiver_city="杭州市",
                receiver_district="西湖区",
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)
        self.assertIn("SKU-002", result.message)

    # === MODIFIED START ===
    # 原因：限发区域模块新增启用开关，关闭时命中区域也不能进入异常。
    # 影响范围：RegionRule 禁用行为。
    def test_disabled_module_returns_pass_even_when_region_matches(self) -> None:
        rule = RegionRule(
            restricted_regions=[
                RestrictedRegion(sku_code="SKU-001", province="浙江省", city="杭州市"),
            ],
            enabled=False,
        )

        result = rule.evaluate(
            RuleContext(
                order_no="SO-002",
                sku_codes=("SKU-001",),
                receiver_province="浙江省",
                receiver_city="杭州市",
                receiver_district="西湖区",
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
    # === MODIFIED END ===
