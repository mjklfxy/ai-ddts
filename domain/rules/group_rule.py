from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult
from domain.sku_group_info import SkuGroupInfo


class GroupRule(OrderRule):
    """Fails an order when any SKU has no configured push group."""

    rule_name = "GroupRule"

    # === MODIFIED START ===
    # 原因：SKU 群配置模块需要支持模块级启用开关。
    # 影响范围：GroupRule 规则判断。
    def __init__(self, sku_group_map: dict[str, SkuGroupInfo], enabled: bool = True) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        self.enabled = enabled
        self.sku_group_map: dict[str, SkuGroupInfo] = {}
        for sku, info in sku_group_map.items():
            key = sku.strip()
            if not key:
                continue
            if not isinstance(info, SkuGroupInfo):
                continue
            if not info.group_name.strip():
                continue
            self.sku_group_map[key] = info
    # === MODIFIED END ===

    def evaluate(self, context: RuleContext) -> RuleResult:
        # === MODIFIED START ===
        # 原因：模块关闭时不把缺少群配置作为规则异常。
        # 影响范围：GroupRule 返回决策。
        if not self.enabled:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )
        # === MODIFIED END ===
        missing_group_skus = self._missing_group_skus(context)
        if missing_group_skus:
            return RuleResult(
                decision=RuleDecision.ERROR,
                rule_name=self.rule_name,
                reason="未配置推送群",
                message=(
                    f"Order {context.order_no} has SKUs without push group: "
                    f"{', '.join(missing_group_skus)}."
                ),
            )

        return RuleResult(
            decision=RuleDecision.PASS,
            rule_name=self.rule_name,
        )

    def _missing_group_skus(self, context: RuleContext) -> tuple[str, ...]:
        normalized_skus = tuple(
            sku.strip()
            for sku in context.sku_codes
            if sku and sku.strip()
        )
        return tuple(
            sku for sku in normalized_skus
            if sku not in self.sku_group_map
        )
