from __future__ import annotations

from enum import Enum


class ExecutionLogStage(Enum):
    """Task execution stages shown in the visual log page."""

    TASK = "任务"
    FETCH = "抓单"
    RULE = "规则判断"
    FILE = "生成文件"
    MESSAGE = "推送群"
    KINGDEE = "金蝶"
    RECEIPT = "回执"
    # === MODIFIED START ===
    # 原因：临时推送需要独立的执行日志阶段。
    # 影响范围：执行日志页面展示。
    TEMP_PUSH = "临时推送"
    # === MODIFIED END ===


class ExecutionLogResult(Enum):
    """Task execution log result values shown to users."""

    SUCCESS = "成功"
    FAILED = "失败"
    SKIPPED = "跳过"
    PARTIAL = "部分成功"
