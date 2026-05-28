from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


# === MODIFIED START ===
# 原因：临时推送需要正选 SKU 白名单规则，命中→PASS，未命中→IGNORE。
# 影响范围：临时推送规则引擎。
class SpecialSkuRule(OrderRule):
    """Positive SKU selection: PASS if SKU is in the list, IGNORE otherwise."""

    rule_name = "SpecialSku"

    def __init__(self, special_skus: set[str], enabled: bool = True) -> None:
        self.special_skus = {s.strip() for s in special_skus if s.strip()}
        self.enabled = enabled

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not self.enabled or not self.special_skus:
            return RuleResult(decision=RuleDecision.IGNORE, rule_name=self.rule_name)
        for sku in context.sku_codes:
            if sku.strip() in self.special_skus:
                return RuleResult(decision=RuleDecision.PASS, rule_name=self.rule_name)
        return RuleResult(decision=RuleDecision.IGNORE, rule_name=self.rule_name)
# === MODIFIED END ===
