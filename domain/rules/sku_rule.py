from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


class SkuServiceRule(OrderRule):
    """Ignores an order when any SKU is configured as excluded from direct push."""

    rule_name = "SkuServiceRule"

    # === MODIFIED START ===
    # 原因：SKU 规则实际是排除逻辑，不是服务启用白名单；命中排除 SKU 应整单忽略。
    # 影响范围：SkuServiceRule 规则语义和规则引擎结果。
    def __init__(
        self,
        excluded_skus: set[str] | list[str] | tuple[str, ...],
        enabled: bool = True,
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        self.enabled = enabled
        self.excluded_skus = {
            sku.strip()
            for sku in excluded_skus
            if sku and sku.strip()
        }
    # === MODIFIED END ===

    def evaluate(self, context: RuleContext) -> RuleResult:
        # === MODIFIED START ===
        # 原因：排除 SKU 模块需要支持总开关；关闭时不应用 SKU 排除列表。
        # 影响范围：SKU 规则返回决策和异常订单生成。
        if not self.enabled:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )

        excluded_skus = self._matched_excluded_skus(context)
        if excluded_skus:
            return RuleResult(
                decision=RuleDecision.IGNORE,
                rule_name=self.rule_name,
                reason="SKU排除",
                message=(
                    f"Order {context.order_no} ignored by excluded SKUs: "
                    f"{', '.join(excluded_skus)}."
                ),
            )
        # === MODIFIED END ===

        return RuleResult(
            decision=RuleDecision.PASS,
            rule_name=self.rule_name,
        )

    # === MODIFIED START ===
    # 原因：规则从“未启用 SKU”改为“排除 SKU”，匹配方法同步改名。
    # 影响范围：SkuServiceRule 内部匹配逻辑。
    def _matched_excluded_skus(self, context: RuleContext) -> tuple[str, ...]:
        normalized_skus = tuple(
            sku.strip()
            for sku in context.sku_codes
            if sku and sku.strip()
        )
        return tuple(
            sku for sku in normalized_skus
            if sku in self.excluded_skus
        )
    # === MODIFIED END ===
