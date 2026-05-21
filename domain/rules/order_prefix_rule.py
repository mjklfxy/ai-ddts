from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


class OrderPrefixRule(OrderRule):
    """Ignores orders whose order_no does not start with any allowed prefix."""

    rule_name = "OrderPrefixRule"

    def __init__(
        self,
        allowed_prefixes: tuple[str, ...],
        enabled: bool = True,
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        self.enabled = enabled
        self.allowed_prefixes = tuple(
            prefix.strip()
            for prefix in allowed_prefixes
            if prefix and prefix.strip()
        )

    def evaluate(self, context: RuleContext) -> RuleResult:
        if not self.enabled:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )

        if not self.allowed_prefixes:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )

        for prefix in self.allowed_prefixes:
            if context.order_no.startswith(prefix):
                return RuleResult(
                    decision=RuleDecision.PASS,
                    rule_name=self.rule_name,
                )

        return RuleResult(
            decision=RuleDecision.IGNORE,
            rule_name=self.rule_name,
            reason="订单号前缀不在白名单",
            message=(
                f"Order {context.order_no} does not start with any allowed prefix: "
                f"{', '.join(self.allowed_prefixes)}."
            ),
        )
