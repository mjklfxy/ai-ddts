from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkuGroupInfo:
    """Push group configuration for a SKU."""

    group_name: str
    owner_mobile: str
    user_id: str = ""
