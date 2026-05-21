from __future__ import annotations

from enum import Enum


class ExceptionProcessStatus(Enum):
    """Exception order processing status values."""

    PENDING = "待处理"
    PROCESSED = "已处理"
