from __future__ import annotations

from enum import Enum


class RuleDecision(Enum):
    """Decision returned by every order rule."""

    PASS = "PASS"
    IGNORE = "IGNORE"
    ERROR = "ERROR"
