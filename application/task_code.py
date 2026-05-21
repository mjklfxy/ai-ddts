from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
import re


Clock = Callable[[], datetime]
ExistingCodesProvider = Callable[[], Iterable[str]]

TASK_CODE_PATTERN = re.compile(r"^(?P<date>\d{8})(?P<sequence>\d{4})$")


class DailyTaskCodeGenerator:
    """Generates task batch codes as yyyyMMdd plus a four-digit daily sequence."""

    def __init__(
        self,
        existing_codes_provider: ExistingCodesProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.existing_codes_provider = existing_codes_provider or tuple
        self.clock = clock or datetime.now
        self._last_date_prefix: str | None = None
        self._last_sequence = 0

    def __call__(self) -> str:
        now = self.clock()
        date_prefix = now.strftime("%Y%m%d")
        current_sequence = max_existing_sequence(
            existing_codes=self.existing_codes_provider(),
            date_prefix=date_prefix,
        )
        if self._last_date_prefix == date_prefix:
            current_sequence = max(current_sequence, self._last_sequence)

        next_sequence = current_sequence + 1
        if next_sequence > 9999:
            raise ValueError("daily task code sequence exceeded 9999")

        self._last_date_prefix = date_prefix
        self._last_sequence = next_sequence
        return f"{date_prefix}{next_sequence:04d}"


def max_existing_sequence(existing_codes: Iterable[str], date_prefix: str) -> int:
    """Returns the largest sequence already used for one yyyyMMdd prefix."""

    if not isinstance(date_prefix, str) or not re.fullmatch(r"\d{8}", date_prefix):
        raise ValueError("date_prefix must be yyyyMMdd")

    max_sequence = 0
    for code in existing_codes:
        if not isinstance(code, str):
            continue
        match = TASK_CODE_PATTERN.fullmatch(code.strip())
        if match is None or match.group("date") != date_prefix:
            continue
        max_sequence = max(max_sequence, int(match.group("sequence")))
    return max_sequence
