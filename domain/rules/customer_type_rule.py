from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


class CustomerTypeRule(OrderRule):
    """Ignores orders whose order_no contains the personal-order suffix."""

    rule_name = "CustomerTypeRule"

    def __init__(
        self,
        personal_order_suffix: str = "-MULTI",
        enabled: bool = True,
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        if not isinstance(personal_order_suffix, str) or not personal_order_suffix.strip():
            raise ValueError("personal_order_suffix must be a non-empty string")
        self.enabled = enabled
        self.personal_order_suffix = personal_order_suffix.strip()

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not self.enabled:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )
        if self.personal_order_suffix in context.order_no:
            return RuleResult(
                decision=RuleDecision.IGNORE,
                rule_name=self.rule_name,
                reason="个人顾客订单过滤",
                message=f"Order {context.order_no} ignored by personal order suffix {self.personal_order_suffix}.",
            )

        return RuleResult(
            decision=RuleDecision.PASS,
            rule_name=self.rule_name,
        )
