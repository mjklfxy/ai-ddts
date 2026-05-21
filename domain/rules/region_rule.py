from __future__ import annotations

from dataclasses import dataclass

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


@dataclass(frozen=True, slots=True)
class RestrictedRegion:
    """SKU-level restricted delivery region."""

    sku_code: str
    province: str
    city: str | None = None
    district: str | None = None

    def matches(
        self,
        province: str | None,
        city: str | None,
        district: str | None,
    ) -> bool:
        if self._normalize(province) != self._normalize(self.province):
            return False

        if self.city and self._normalize(city) != self._normalize(self.city):
            return False

        if self.district and self._normalize(district) != self._normalize(self.district):
            return False

        return True

    @staticmethod
    def _normalize(value: str | None) -> str:
        return value.strip() if value else ""


class RegionRule(OrderRule):
    """Fails an order when any SKU matches a restricted delivery region."""

    rule_name = "RegionRule"

    # === MODIFIED START ===
    # 原因：限发区域模块需要支持模块级启用开关。
    # 影响范围：RegionRule 规则判断。
    def __init__(
        self,
        restricted_regions: list[RestrictedRegion] | tuple[RestrictedRegion, ...],
        enabled: bool = True,
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        self.enabled = enabled
        self.restricted_regions_by_sku: dict[str, tuple[RestrictedRegion, ...]] = {}
        grouped_regions: dict[str, list[RestrictedRegion]] = {}
        for region in restricted_regions:
            sku_code = region.sku_code.strip()
            if not sku_code:
                continue
            grouped_regions.setdefault(sku_code, []).append(region)

        self.restricted_regions_by_sku = {
            sku_code: tuple(regions)
            for sku_code, regions in grouped_regions.items()
        }
    # === MODIFIED END ===

    def evaluate(self, context: RuleContext) -> RuleResult:
        # === MODIFIED START ===
        # 原因：模块关闭时不应用限发区域列表。
        # 影响范围：RegionRule 返回决策。
        if not self.enabled:
            return RuleResult(
                decision=RuleDecision.PASS,
                rule_name=self.rule_name,
            )
        # === MODIFIED END ===
        matched = self._matched_region(context)
        if matched is not None:
            sku_code, region = matched
            return RuleResult(
                decision=RuleDecision.ERROR,
                rule_name=self.rule_name,
                reason="命中限发区域",
                message=(
                    f"Order {context.order_no} SKU {sku_code} matched restricted region "
                    f"{region.province}/{region.city or '*'}/{region.district or '*'}."
                ),
            )

        return RuleResult(
            decision=RuleDecision.PASS,
            rule_name=self.rule_name,
        )

    def _matched_region(self, context: RuleContext) -> tuple[str, RestrictedRegion] | None:
        for sku_code in context.sku_codes:
            regions = self.restricted_regions_by_sku.get(sku_code.strip(), ())
            for region in regions:
                if region.matches(
                    province=context.receiver_province,
                    city=context.receiver_city,
                    district=context.receiver_district,
                ):
                    return sku_code, region
        return None
