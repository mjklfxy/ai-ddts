from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupplierInfo:
    """Supplier mapping data synced from ERP for one SKU."""

    sku_code: str
    # === MODIFIED START ===
    # 原因：SKU-供应商对照不再需要供应商编码，只保留商品名称与供应商名称关系。
    # 影响范围：供应商对照数据模型、金蝶提交和订单明细导出。
    # === MODIFIED END ===
    supplier_name: str


# === MODIFIED START ===
# 原因：供应商缺失从订单推送前置规则改为金蝶资料校验，需要跨层传递明确失败原因。
# 影响范围：金蝶提交阶段与 Pipeline 异常明细生成。
class MissingSupplierError(ValueError):
    """Raised when purchase request data lacks supplier mapping for SKUs."""

    def __init__(self, missing_skus: tuple[str, ...]) -> None:
        self.missing_skus = tuple(sorted(set(missing_skus)))
        super().__init__(f"未配置供应商：{', '.join(self.missing_skus)}")
# === MODIFIED END ===
