from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from domain.enums.rule import RuleDecision
from domain.rules.base import OrderRule, RuleContext, RuleResult


LogInfo = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class RuleEngineResult:
    """Final rule evaluation result for one order."""

    decision: RuleDecision
    results: tuple[RuleResult, ...]

    @property
    def final_result(self) -> RuleResult:
        if not self.results:
            raise ValueError("RuleEngineResult has no rule results")
        return self.results[-1]

    @property
    def is_pass(self) -> bool:
        return self.decision is RuleDecision.PASS

    @property
    def is_ignore(self) -> bool:
        return self.decision is RuleDecision.IGNORE

    @property
    def is_error(self) -> bool:
        return self.decision is RuleDecision.ERROR


class RuleEngine:
    """Runs order rules in sequence and records rule hit logs."""

    def __init__(
        self,
        rules: Sequence[OrderRule],
        log_info: LogInfo | None = None,
    ) -> None:
        self.rules = tuple(rules)
        self.log_info = log_info or self._noop_log_info

    def evaluate(self, context: RuleContext) -> RuleEngineResult:
        results: list[RuleResult] = []

        for rule in self.rules:
            result = rule.evaluate(context)
            results.append(result)
            self._log_rule_hit(context=context, result=result)

            if result.decision is not RuleDecision.PASS:
                return RuleEngineResult(
                    decision=result.decision,
                    results=tuple(results),
                )

        return RuleEngineResult(
            decision=RuleDecision.PASS,
            results=tuple(results),
        )

    def _log_rule_hit(self, context: RuleContext, result: RuleResult) -> None:
        self.log_info(
            "rule_hit",
            {
                "trace_id": context.trace_id,
                "order_no": context.order_no,
                "rule_name": result.rule_name,
                "decision": result.decision.value,
                "reason": result.reason,
            },
        )

    @staticmethod
    def _noop_log_info(event: str, payload: dict[str, object]) -> None:
        _ = (event, payload)
