from unittest import TestCase

from domain.enums.rule import RuleDecision
from domain.rule_engine import RuleEngine
from domain.rules.base import RuleContext
from domain.rules.group_rule import GroupRule
from domain.rules.sku_rule import SkuServiceRule
from domain.rules.warehouse_rule import WarehouseRule
from domain.sku_group_info import SkuGroupInfo


class RuleEngineTests(TestCase):
    """Tests rule orchestration and rule_hit logging."""

    def test_all_pass_rules_return_pass_and_log_rule_hits(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        engine = RuleEngine(
            rules=[
                WarehouseRule(excluded_warehouses={"WH-001"}),
                # === MODIFIED START ===
                # 原因：SKU 规则改为排除黑名单；空排除列表应通过。
                # 影响范围：RuleEngine 通过链路测试。
                SkuServiceRule(excluded_skus=set()),
                # === MODIFIED END ===
            ],
            log_info=lambda event, payload: logs.append((event, payload)),
        )

        result = engine.evaluate(
            RuleContext(
                order_no="SO-001",
                trace_id="TRACE-001",
                warehouse_code="WH-002",
                sku_codes=("SKU-001",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertTrue(result.is_pass)
        self.assertEqual(len(result.results), 2)
        self.assertEqual([event for event, _ in logs], ["rule_hit", "rule_hit"])
        self.assertEqual([payload["trace_id"] for _, payload in logs], ["TRACE-001", "TRACE-001"])
        self.assertEqual([payload["rule_name"] for _, payload in logs], ["WarehouseRule", "SkuServiceRule"])

    def test_ignore_result_stops_following_rules(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        engine = RuleEngine(
            rules=[
                WarehouseRule(excluded_warehouses={"WH-001"}),
                SkuServiceRule(excluded_skus={"SKU-001"}),
            ],
            log_info=lambda event, payload: logs.append((event, payload)),
        )

        result = engine.evaluate(
            RuleContext(
                order_no="SO-001",
                trace_id="TRACE-001",
                warehouse_code="WH-001",
                sku_codes=("SKU-001",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.IGNORE)
        self.assertTrue(result.is_ignore)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(logs[0][1]["rule_name"], "WarehouseRule")
        self.assertEqual(logs[0][1]["decision"], "IGNORE")
        self.assertEqual(logs[0][1]["reason"], "仓库过滤")

    def test_error_result_stops_following_rules(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        engine = RuleEngine(
            rules=[
                # === MODIFIED START ===
                # 原因：SkuServiceRule 不再产生 ERROR，错误短路改由 GroupRule 覆盖。
                # 影响范围：RuleEngine ERROR 短路测试。
                GroupRule(sku_group_map={"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile="")}),
                # === MODIFIED END ===
                WarehouseRule(excluded_warehouses={"WH-001"}),
            ],
            log_info=lambda event, payload: logs.append((event, payload)),
        )

        result = engine.evaluate(
            RuleContext(
                order_no="SO-001",
                trace_id="TRACE-001",
                warehouse_code="WH-002",
                sku_codes=("SKU-002",),
            )
        )

        self.assertEqual(result.decision, RuleDecision.ERROR)
        self.assertTrue(result.is_error)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(logs[0][1]["rule_name"], "GroupRule")
        self.assertEqual(logs[0][1]["decision"], "ERROR")
        self.assertEqual(logs[0][1]["reason"], "未配置推送群")

    def test_no_rules_return_pass(self) -> None:
        logs: list[tuple[str, dict[str, object]]] = []
        engine = RuleEngine(
            rules=[],
            log_info=lambda event, payload: logs.append((event, payload)),
        )

        result = engine.evaluate(
            RuleContext(
                order_no="SO-001",
                trace_id="TRACE-001",
            )
        )

        self.assertEqual(result.decision, RuleDecision.PASS)
        self.assertEqual(result.results, ())
        self.assertEqual(logs, [])
