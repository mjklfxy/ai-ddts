from __future__ import annotations

from enum import Enum


class PushStatus(Enum):
    """Push status values exposed to users and APIs."""

    PENDING = "待推送"
    SUCCESS = "已推送"
    # === MODIFIED START ===
    # 原因：厂家群推送可能出现部分批次成功、部分批次失败，需要单独状态提醒用户查看详情。
    # 影响范围：任务推送状态枚举、任务历史响应和前端筛选展示。
    PARTIAL = "部分推送"
    # === MODIFIED END ===
    FAILED = "推送失败"


class PaymentStatus(Enum):
    """Payment status values for task receipts."""

    UNPAID = "未付款"
    PAID = "已付款"


class KingdeeStatus(Enum):
    """Kingdee purchase request status values."""

    # === MODIFIED START ===
    # 原因：产品预设金蝶推送可关闭，关闭时状态必须使用 Enum 表达。
    # 影响范围：任务历史、接口响应和前端状态展示。
    DISABLED = "未启用"
    # === MODIFIED END ===
    PENDING = "采购申请单待提交"
    SUCCESS = "采购申请单已提交"
    FAILED = "采购申请单提交失败"


# === MODIFIED START ===
# 原因：Scheduler 执行结果也属于状态类字段，必须使用 Enum。
# 影响范围：调度器状态与接口响应。
class SchedulerStatus(Enum):
    """Scheduler tick status values exposed to APIs."""

    DISABLED = "未启用"
    NOT_DUE = "未到时间"
    ALREADY_RAN = "今日已运行"
    RAN = "已运行"
# === MODIFIED END ===
