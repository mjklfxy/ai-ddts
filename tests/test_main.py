import json
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.config_service import ConfigService
from application.manual_runner import build_jikeyun_client_from_config, build_kingdee_transport_from_config
from application.task_service import TaskService
from domain.enums.status import KingdeeStatus, PushStatus
from infrastructure.jikeyun_client import JikeyunPageResult
from infrastructure.kingdee_service import KingdeeService
from main import RunSummary, run_once


class MainRunTests(TestCase):
    """Tests manual local pipeline runs."""

    def test_run_once_with_demo_config_returns_summary(self) -> None:
        config_path = write_demo_config()
        # === MODIFIED START ===
        # 原因：任务运行金蝶提交阶段需要准备 ERP SKU-供应商对照数据。
        # 影响范围：手动运行测试。
        supplier_mapping_path = write_supplier_mappings()
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务运行会持久化异常订单，测试使用独立临时文件。
        # 影响范围：手动运行测试。
        exception_order_path = Path("tmp") / "test_main" / "exception_orders.json"
        if exception_order_path.exists():
            exception_order_path.unlink()
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务运行会持久化正常推送订单明细，测试使用独立临时文件。
        # 影响范围：手动运行测试。
        pushed_order_path = Path("tmp") / "test_main" / "pushed_orders.json"
        if pushed_order_path.exists():
            pushed_order_path.unlink()
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务运行会持久化可视化执行日志，测试使用独立临时文件。
        # 影响范围：手动运行测试。
        execution_log_path = Path("tmp") / "test_main" / "execution_logs.json"
        if execution_log_path.exists():
            execution_log_path.unlink()
        # === MODIFIED END ===

        summary = run_once(
            config_path=config_path,
            supplier_mapping_path=supplier_mapping_path,
            # === MODIFIED START ===
            # 原因：手动运行入口需要支持基于历史批次号生成当天四位数累计编码。
            # 影响范围：run_once 任务上下文创建测试。
            existing_task_codes_provider=lambda: ("202604300001",),
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：隔离异常订单持久化测试文件。
            # 影响范围：手动运行测试。
            exception_order_path=exception_order_path,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：隔离正常推送订单明细持久化测试文件。
            # 影响范围：手动运行测试。
            pushed_order_path=pushed_order_path,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：隔离执行日志持久化测试文件。
            # 影响范围：手动运行测试。
            execution_log_path=execution_log_path,
            # === MODIFIED END ===
        )

        self.assertIsInstance(summary, RunSummary)
        # === MODIFIED START ===
        # 原因：任务批次编码规则改为当天日期 + 四位数累计。
        # 影响范围：run_once 返回摘要。
        self.assertEqual(summary.trace_id, "202604300002")
        # === MODIFIED END ===
        self.assertEqual(summary.passed_count, 4)
        self.assertEqual(summary.ignored_count, 1)
        self.assertEqual(summary.error_count, 1)
        self.assertEqual(summary.delivery_count, 1)
        # === MODIFIED START ===
        # 原因：金蝶推送当前默认不启用，任务应跳过采购申请提交。
        # 影响范围：run_once 默认摘要。
        self.assertIsNone(summary.kingdee_tracking_id)
        self.assertEqual(summary.kingdee_status, KingdeeStatus.DISABLED)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：确认规则失败订单已生成异常订单记录。
        # 影响范围：手动运行测试断言。
        persisted = json.loads(exception_order_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted[0]["order_no"], "SO-LOCAL-ERROR")
        self.assertEqual(persisted[0]["reason"], "未配置推送群")
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：确认正常推送订单明细已按 SKU-供应商对照补充供应商信息。
        # 影响范围：正常推送订单明细下载数据源。
        pushed_records = json.loads(pushed_order_path.read_text(encoding="utf-8"))
        self.assertEqual(pushed_records[0]["order_no"], "SO-LOCAL-PASS")
        self.assertEqual(pushed_records[0]["supplier_name"], "Supplier A")
        self.assertNotIn("supplier_code", pushed_records[0])
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务执行过程需要形成面向业务人员的可视化日志。
        # 影响范围：run_once 执行日志。
        execution_logs = json.loads(execution_log_path.read_text(encoding="utf-8"))
        self.assertEqual(execution_logs[0]["trace_id"], "202604300002")
        self.assertEqual(
            {item["stage"] for item in execution_logs},
            {"任务", "抓单", "规则判断", "生成文件", "推送群", "金蝶"},
        )
        self.assertIn("任务执行完成", [item["summary"] for item in execution_logs])
        # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：供应商缺失只影响金蝶提交，不应阻断外部群订单推送。
    # 影响范围：手动运行流程边界。
    def test_run_once_missing_supplier_still_pushes_orders_and_fails_kingdee(self) -> None:
        config_path = write_demo_config(kingdee_enabled=True)
        supplier_mapping_path = Path("tmp") / "test_main" / "missing_supplier_mappings.json"
        if supplier_mapping_path.exists():
            supplier_mapping_path.unlink()
        exception_order_path = Path("tmp") / "test_main" / "exception_orders_missing_supplier.json"
        if exception_order_path.exists():
            exception_order_path.unlink()
        # === MODIFIED START ===
        # 原因：缺供应商场景同样要隔离正常推送订单明细持久化文件。
        # 影响范围：手动运行流程边界测试。
        pushed_order_path = Path("tmp") / "test_main" / "pushed_orders_missing_supplier.json"
        if pushed_order_path.exists():
            pushed_order_path.unlink()
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：缺供应商场景同样隔离执行日志。
        # 影响范围：手动运行流程边界测试。
        execution_log_path = Path("tmp") / "test_main" / "execution_logs_missing_supplier.json"
        if execution_log_path.exists():
            execution_log_path.unlink()
        # === MODIFIED END ===

        summary = run_once(
            config_path=config_path,
            supplier_mapping_path=supplier_mapping_path,
            exception_order_path=exception_order_path,
            # === MODIFIED START ===
            # 原因：缺供应商不阻断外部群推送，但正常推送明细应持久化为空供应商。
            # 影响范围：正常推送订单明细下载数据源。
            pushed_order_path=pushed_order_path,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：缺供应商流程也需要持久化执行日志。
            # 影响范围：手动运行流程边界测试。
            execution_log_path=execution_log_path,
            # === MODIFIED END ===
            trace_id_generator=lambda: "TRACE-MISSING-SUPPLIER",
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertEqual(summary.passed_count, 4)
        self.assertEqual(summary.ignored_count, 1)
        # === MODIFIED START ===
        # 原因：SKU-供应商对照缺失不计入异常订单。
        # 影响范围：手动运行任务异常统计。
        self.assertEqual(summary.error_count, 1)
        # === MODIFIED END ===
        self.assertEqual(summary.delivery_count, 1)
        self.assertEqual(summary.push_status, PushStatus.SUCCESS)
        self.assertEqual(summary.kingdee_status, KingdeeStatus.FAILED)
        self.assertEqual(summary.failure_stage, "kingdee_submit")
        self.assertIn("未配置供应商", summary.failure_reason)
        self.assertIsNone(summary.kingdee_tracking_id)

        persisted = json.loads(exception_order_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted((item["order_no"], item["reason"]) for item in persisted),
            [
                ("SO-LOCAL-ERROR", "未配置推送群"),
            ],
        )
        # === MODIFIED START ===
        # 原因：缺供应商时外部群推送仍成功，正常推送订单明细应保留且供应商为空。
        # 影响范围：正常推送订单明细下载数据源。
        pushed_records = json.loads(pushed_order_path.read_text(encoding="utf-8"))
        self.assertEqual(pushed_records[0]["order_no"], "SO-LOCAL-PASS")
        self.assertEqual(pushed_records[0]["supplier_name"], "")
        self.assertNotIn("supplier_code", pushed_records[0])
        # === MODIFIED END ===
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：真实吉客云来源需要从环境变量读取认证，并把配置传给客户端。
    # 影响范围：订单来源客户端构建。
    def test_build_jikeyun_client_from_config_uses_env_credentials_and_query_config(self) -> None:
        config = ConfigService().from_dict(
            {
                "task": {
                    "name": "daily-direct-order",
                    "window_minutes": 240,
                },
                "source": {
                    "mode": "jikeyun",
                },
                "jikeyun": {
                    "api_url": "https://example.test/openapi",
                    "app_key_env": "APP_KEY_ENV",
                    "app_secret_env": "APP_SECRET_ENV",
                    "page_size": 20,
                    "status_field": "orderStatusList",
                    "status_values": [0, 1, 3],
                    "extra_params": {
                        "shopId": "SHOP-001",
                    },
                    "page_index_base": 0,
                },
                "rules": {},
                "message": {
                    "max_attempts": 1,
                    "retry_interval_seconds": 0,
                },
                "output": {
                    "order_file_dir": "tmp/test_main/order_files",
                },
            }
        )
        requests = []

        def transport(request):
            requests.append(request)
            return JikeyunPageResult(items=(), has_next=False)

        client = build_jikeyun_client_from_config(
            config=config,
            env={
                "APP_KEY_ENV": "APPKEY",
                "APP_SECRET_ENV": "SECRET",
            },
            transport=transport,
        )

        client.fetch_orders(
            trace_id="TRACE-001",
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertEqual(requests[0].app_key, "APPKEY")
        self.assertEqual(requests[0].page_no, 0)
        self.assertEqual(requests[0].page_size, 20)
        self.assertEqual(requests[0].biz_content["orderStatusList"], [0, 1, 3])
        self.assertEqual(requests[0].biz_content["shopId"], "SHOP-001")

    def test_build_jikeyun_client_rejects_missing_env_credentials(self) -> None:
        config = ConfigService().from_dict(
            {
                "task": {
                    "name": "daily-direct-order",
                    "window_minutes": 240,
                },
                "source": {
                    "mode": "jikeyun",
                },
                "rules": {},
                "message": {
                    "max_attempts": 1,
                    "retry_interval_seconds": 0,
                },
                "output": {
                    "order_file_dir": "tmp/test_main/order_files",
                },
            }
        )

        with self.assertRaisesRegex(ValueError, "JIKEYUN_APPKEY"):
            build_jikeyun_client_from_config(config=config, env={})
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：金蝶 HTTP transport 需要由配置构建，并从环境变量读取 token。
    # 影响范围：任务运行金蝶提交配置。
    def test_build_kingdee_transport_from_config_uses_http_config_and_env_token(self) -> None:
        config = ConfigService().from_dict(
            {
                "task": {
                    "name": "daily-direct-order",
                    "window_minutes": 240,
                },
                "kingdee": {
                    "mode": "http",
                    "api_url": "https://kingdee.example.test/purchase",
                    "token_env": "KD_TOKEN",
                    "timeout_seconds": 10,
                    "tracking_id_fields": ["billNo"],
                    "extra_headers": {
                        "X-App": "direct-order",
                    },
                },
                "rules": {},
                "message": {
                    "max_attempts": 1,
                    "retry_interval_seconds": 0,
                },
                "output": {
                    "order_file_dir": "tmp/test_main/order_files",
                },
            }
        )

        transport = build_kingdee_transport_from_config(
            config=config,
            env={"KD_TOKEN": "TOKEN-001"},
        )

        self.assertEqual(transport.api_url, "https://kingdee.example.test/purchase")
        self.assertEqual(transport.token, "TOKEN-001")
        self.assertEqual(transport.timeout_seconds, 10)
        self.assertEqual(transport.tracking_id_fields, ("billNo",))

    def test_build_kingdee_transport_defaults_to_local_tracking_id(self) -> None:
        config = ConfigService().load(write_demo_config())
        transport = build_kingdee_transport_from_config(config=config)
        request = KingdeeService(transport=transport).build_purchase_request(
            task_context=TaskService(
                trace_id_generator=lambda: "TRACE-LOCAL",
                clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
            ).create_task(
                task_name="daily-direct-order",
                window_start=datetime(2026, 4, 30, 8, 0, 0),
                window_end=datetime(2026, 4, 30, 12, 0, 0),
            ),
            deliveries=(),
        )

        self.assertEqual(transport(request).tracking_id, "LOCAL-KINGDEE-TRACE-LOCAL")
    # === MODIFIED END ===


def write_demo_config(kingdee_enabled: bool = False) -> Path:
    """Writes a deterministic config file for manual run tests."""

    config_path = Path("tmp") / "test_main" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "task": {
                    "name": "daily-direct-order",
                    "window_minutes": 240,
                },
                # === MODIFIED START ===
                # 原因：金蝶推送当前默认不启用，个别测试可显式打开。
                # 影响范围：手动运行测试配置。
                "kingdee": {
                    "enabled": kingdee_enabled,
                    "mode": "mock",
                    "api_url": "",
                    "token_env": "KINGDEE_TOKEN",
                    "timeout_seconds": 30,
                    "tracking_id_fields": ["tracking_id", "trackingId", "id", "bill_no", "billNo", "number"],
                    "extra_headers": {},
                },
                # === MODIFIED END ===
                "rules": {
                    # === MODIFIED START ===
                    # 原因：手动运行测试配置显式声明规则模块开关，确保 Pipeline 构建读取真实开关。
                    # 影响范围：手动运行测试配置。
                    "excluded_warehouses_enabled": True,
                    # === MODIFIED END ===
                    "excluded_warehouses": ["WH-IGNORE"],
                    # === MODIFIED START ===
                    # 原因：SKU 规则改为排除黑名单，demo 配置不排除 SKU 且默认关闭模块。
                    # 影响范围：手动运行测试配置。
                    "excluded_skus_enabled": False,
                    "excluded_skus": [],
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：手动运行测试配置显式声明限发区域和 SKU 群配置模块开关。
                    # 影响范围：手动运行测试配置。
                    "restricted_regions_enabled": False,
                    # === MODIFIED END ===
                    "restricted_regions": [],
                    # === MODIFIED START ===
                    # 原因：通过订单仍需要按 SKU 群配置拆分推送文件。
                    # 影响范围：手动运行测试配置。
                    "sku_group_map_enabled": True,
                    # === MODIFIED END ===
                    "sku_group_map": {
                        "SKU-PASS": "GROUP-A",
                    },
                },
                "message": {
                    "max_attempts": 2,
                    "retry_interval_seconds": 0,
                },
                "output": {
                    "order_file_dir": "tmp/test_main/order_files",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path


# === MODIFIED START ===
# 原因：为金蝶提交阶段准备测试用 SKU-供应商映射。
# 影响范围：手动运行测试数据。
def write_supplier_mappings() -> Path:
    """Writes deterministic supplier mappings for manual run tests."""

    mapping_path = Path("tmp") / "test_main" / "sku_supplier_mappings.json"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "sku_code": "SKU-PASS",
                        "supplier_name": "Supplier A",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return mapping_path
# === MODIFIED END ===
