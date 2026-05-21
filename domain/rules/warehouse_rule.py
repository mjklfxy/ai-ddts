from __future__ import annotations

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


class WarehouseRule(OrderRule):
    """Ignores orders whose warehouse is configured as excluded."""

    rule_name = "WarehouseRule"

    # === MODIFIED START ===
    # 原因：排除库房模块需要支持和排除 SKU 一致的模块级启用开关。
    # 影响范围：WarehouseRule 规则判断。
    def __init__(
        self,
        excluded_warehouses: set[str] | list[str] | tuple[str, ...],
        enabled: bool = True,
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        self.enabled = enabled
        self.excluded_warehouses = {
            warehouse.strip()
            for warehouse in excluded_warehouses
            if warehouse and warehouse.strip()
        }
    # === MODIFIED END ===

    def evaluate(self, context: RuleContext) -> RuleResult:
        # === MODIFIED START ===
        # 原因：模块关闭时不应用排除库房列表。
        # 影响范围：WarehouseRule 返回决策。
        if not self.enabled:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )
        # === MODIFIED END ===
        matched_warehouse = self._matched_warehouse(context)
        if matched_warehouse is not None:
            return RuleResult(
                decision=RuleDecision.IGNORE,
                rule_name=self.rule_name,
                reason="仓库过滤",
                message=f"Order {context.order_no} ignored by warehouse {matched_warehouse}.",
            )

        return RuleResult(
            decision=RuleDecision.PASS,
            rule_name=self.rule_name,
        )

    def _matched_warehouse(self, context: RuleContext) -> str | None:
        candidates = (context.warehouse_code, context.warehouse_name)
        for candidate in candidates:
            if candidate and candidate.strip() in self.excluded_warehouses:
                return candidate.strip()
        return None
