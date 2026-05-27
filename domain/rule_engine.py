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

    # === MODIFIED START ===
    # 原因：Pipeline 需要对整单异常做单 SKU 静默复算以定位连坐根因，不能额外污染规则命中日志。
    # 影响范围：RuleEngine.evaluate 调用方；默认仍记录日志保持兼容。
    def evaluate(self, context: RuleContext, log_hits: bool = True) -> RuleEngineResult:
    # === MODIFIED END ===
        results: list[RuleResult] = []

        for rule in self.rules:
            result = rule.evaluate(context)
            results.append(result)
            # === MODIFIED START ===
            # 原因：单 SKU 根因复算属于内部诊断，不应产生重复 rule_hit。
            # 影响范围：连坐异常原因计算。
            if log_hits:
                self._log_rule_hit(context=context, result=result)
            # === MODIFIED END ===

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
