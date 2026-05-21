from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.enums.rule import RuleDecision


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Order data needed by pure business rules."""

    order_no: str
    # === MODIFIED START ===
    # 原因：任务6 RuleEngine 日志必须包含 trace_id，需要在规则上下文中携带追踪号。
    # 影响范围：domain 规则上下文，默认空字符串兼容既有测试。
    trace_id: str = ""
    # === MODIFIED END ===
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    # === MODIFIED START ===
    # 原因：规则中的 SKU 口径明确为订单明细“商品名称”，规则上下文需要携带商品名称列表。
    # 影响范围：domain 规则上下文，兼容既有 WarehouseRule 测试的默认空元组。
    sku_codes: tuple[str, ...] = ()
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：任务4 RegionRule 需要读取收货省市区，用于 SKU 限发区域整单判断。
    # 影响范围：domain 规则上下文，新增字段均有默认值，兼容既有规则和测试。
    receiver_province: str | None = None
    receiver_city: str | None = None
    receiver_district: str | None = None
    # === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Standard result returned by every order rule."""

    decision: RuleDecision
    rule_name: str
    reason: str | None = None
    message: str | None = None

    @property
    def is_pass(self) -> bool:
        return self.decision is RuleDecision.PASS

    @property
    def is_ignore(self) -> bool:
        return self.decision is RuleDecision.IGNORE

    @property
    def is_error(self) -> bool:
        return self.decision is RuleDecision.ERROR


class OrderRule(ABC):
    """Base class for all pure order business rules."""

    rule_name: str

    @abstractmethod
    def evaluate(self, context: RuleContext) -> RuleResult:
        """Evaluate an order and return a RuleResult."""
