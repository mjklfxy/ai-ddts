from __future__ import annotations

from dataclasses import dataclass

from domain.enums.exception import ExceptionProcessStatus
from domain.rules.base import RuleResult


@dataclass(frozen=True, slots=True)
class ExceptionOrderSource:
    """Order fields required by exception order exports."""

    order_no: str
    # === MODIFIED START ===
    # 原因：异常订单需要标识触发异常的商品名称，便于定位限发、未配置群等规则异常。
    # 影响范围：异常订单模型与导出字段注释。
    sku_code: str
    # === MODIFIED END ===
    delivery_order_no: str
    goods_summary: str
    # === MODIFIED START ===
    # 原因：抓单结果需要保留仓库字段，异常订单明细也要能带出仓库。
    # 影响范围：异常订单来源模型。
    warehouse_code: str
    warehouse_name: str
    # === MODIFIED END ===
    quantity: int
    receiver_name: str
    address: str
    phone: str
    logistics_company: str = ""
    logistics_no: str = ""
    # === MODIFIED START ===
    # 原因：异常订单明细需要记录 SKU 对应的推送群和供应商信息，供前端查看和下载。
    # 影响范围：ExceptionOrderSource、ExceptionOrder 与持久化。
    group_name: str = ""
    owner_mobile: str = ""
    supplier_name: str = ""
    channel_classification: str = ""
    # === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class ExceptionOrder:
    """Exception order detail for download and manual processing."""

    order_no: str
    # === MODIFIED START ===
    # 原因：异常订单明细需要输出 SKU 维度，支持后续统计和人工处理。
    # 影响范围：异常订单明细与导出。
    sku_code: str
    # === MODIFIED END ===
    delivery_order_no: str
    goods_summary: str
    # === MODIFIED START ===
    # 原因：异常订单查询和下载需要展示订单所属仓库。
    # 影响范围：异常订单明细字段。
    warehouse_code: str
    warehouse_name: str
    # === MODIFIED END ===
    quantity: int
    receiver_name: str
    address: str
    phone: str
    logistics_company: str
    logistics_no: str
    reason: str
    rule_name: str
    # === MODIFIED START ===
    # 原因：异常订单明细需要记录 SKU 对应的推送群和供应商信息，供前端查看和下载。
    # 影响范围：ExceptionOrder、持久化 JSON/CSV 与 API 响应。
    group_name: str = ""
    owner_mobile: str = ""
    supplier_name: str = ""
    channel_classification: str = ""
    # === MODIFIED END ===
    process_status: ExceptionProcessStatus = ExceptionProcessStatus.PENDING

    @classmethod
    def from_rule_result(
        cls,
        source: ExceptionOrderSource,
        rule_result: RuleResult,
        process_status: ExceptionProcessStatus = ExceptionProcessStatus.PENDING,
    ) -> "ExceptionOrder":
        if not rule_result.reason:
            raise ValueError("Exception order rule result must include reason")

        if not rule_result.rule_name:
            raise ValueError("Exception order rule result must include rule_name")

        return cls(
            order_no=source.order_no,
            # === MODIFIED START ===
            # 原因：从异常来源保留 SKU 编码，供查询和下载使用。
            # 影响范围：ExceptionOrder.from_rule_result。
            sku_code=source.sku_code,
            # === MODIFIED END ===
            delivery_order_no=source.delivery_order_no,
            goods_summary=source.goods_summary,
            # === MODIFIED START ===
            # 原因：从异常来源保留仓库字段，供查询和下载使用。
            # 影响范围：ExceptionOrder.from_rule_result。
            warehouse_code=source.warehouse_code,
            warehouse_name=source.warehouse_name,
            # === MODIFIED END ===
            quantity=source.quantity,
            receiver_name=source.receiver_name,
            address=source.address,
            phone=source.phone,
            logistics_company=source.logistics_company,
            logistics_no=source.logistics_no,
            # === MODIFIED START ===
            # 原因：从异常来源保留推送群和供应商字段。
            # 影响范围：ExceptionOrder.from_rule_result。
            group_name=source.group_name,
            owner_mobile=source.owner_mobile,
            supplier_name=source.supplier_name,
            channel_classification=source.channel_classification,
            # === MODIFIED END ===
            reason=rule_result.reason,
            rule_name=rule_result.rule_name,
            process_status=process_status,
        )
