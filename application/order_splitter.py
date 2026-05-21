from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from domain.sku_group_info import SkuGroupInfo


@dataclass(frozen=True, slots=True)
class OrderLineForSplit:
    """Validated order line prepared for group splitting."""

    order_no: str
    sku_code: str
    delivery_order_no: str
    goods_summary: str
    quantity: int
    receiver_name: str
    address: str
    phone: str
    logistics_company: str = ""
    logistics_no: str = ""
    # === MODIFIED START ===
    # 原因：吉客云订单抓取需要保留仓库字段，供异常订单查询和导出展示。
    # 影响范围：订单行数据在 pipeline 内的传递。
    warehouse_code: str = ""
    warehouse_name: str = ""
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：异常订单明细需要记录 SKU 对应的推送群信息和供应商，供查询和下载。
    # 影响范围：OrderLineForSplit、异常订单来源与持久化。
    group_name: str = ""
    owner_mobile: str = ""
    supplier_name: str = ""
    # === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class GroupOrderBatch:
    """Order lines grouped for one push group."""

    group_name: str
    owner_mobile: str
    user_id: str
    order_lines: tuple[OrderLineForSplit, ...]


class OrderSplitter:
    """Splits already-validated order lines by push group."""

    def __init__(self, sku_group_map: dict[str, SkuGroupInfo]) -> None:
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

    def split(self, order_lines: tuple[OrderLineForSplit, ...] | list[OrderLineForSplit]) -> tuple[GroupOrderBatch, ...]:
        grouped_lines: dict[tuple[str, str, str], list[OrderLineForSplit]] = defaultdict(list)

        for order_line in order_lines:
            info = self.sku_group_map.get(order_line.sku_code.strip())
            if info is None:
                raise ValueError(
                    f"SKU '{order_line.sku_code}' 未配置推送群，"
                    f"请确认 GroupRule 已启用且排在规则链最后"
                )
            key = (info.group_name, info.owner_mobile, info.user_id)
            grouped_lines[key].append(order_line)

        return tuple(
            GroupOrderBatch(
                group_name=group_name,
                owner_mobile=owner_mobile,
                user_id=user_id,
                order_lines=tuple(lines),
            )
            for (group_name, owner_mobile, user_id), lines in sorted(grouped_lines.items())
        )
