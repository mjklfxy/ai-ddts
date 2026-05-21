from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult
from domain.supplier import SupplierInfo


class SupplierRule(OrderRule):
    """Optional pass-through rule for SKU to supplier mapping visibility."""

    rule_name = "SupplierRule"

    def __init__(self, sku_supplier_map: dict[str, SupplierInfo]) -> None:
        self.sku_supplier_map = {
            sku_code.strip(): supplier
            for sku_code, supplier in sku_supplier_map.items()
            if sku_code and sku_code.strip()
        }

    def evaluate(self, context: RuleContext) -> RuleResult:
        # === MODIFIED START ===
        # 原因：SKU-供应商对照缺失不属于订单异常规则，只影响金蝶提交状态。
        # 影响范围：SupplierRule 评估结果，避免未来接入规则引擎后产生异常订单。
        _ = context
        # === MODIFIED END ===
        return RuleResult(
            decision=RuleDecision.PASS,
            rule_name=self.rule_name,
        )
