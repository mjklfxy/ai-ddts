import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from application.config_service import AppConfig, ConfigService
from domain.sku_group_info import SkuGroupInfo


class ConfigServiceTests(TestCase):
    """Tests JSON application configuration loading and validation."""

    def test_loads_default_config_file(self) -> None:
        # === MODIFIED START ===
        # 原因：真实 config/config.json 会被页面保存修改，默认配置测试需要独立 fixture。
        # 影响范围：ConfigService 默认配置加载测试。
        default_config_data = {
            "task": {
                "name": "daily-direct-order",
                "window_minutes": 240,
            },
            "schedule": {
                "schedule_id": "default",
                "name": "默认定时任务",
                "enabled": False,
                "run_at": "09:00",
                "check_interval_seconds": 60,
            },
            "schedules": [
                {
                    "schedule_id": "default",
                    "name": "默认定时任务",
                    "enabled": False,
                    "run_at": "09:00",
                    "check_interval_seconds": 60,
                }
            ],
            "source": {
                "mode": "jikeyun",
            },
            "jikeyun": {
                "api_url": "https://open.jackyun.com/open/openapi/do",
                "app_key_env": "JIKEYUN_APPKEY",
                "app_secret_env": "JIKEYUN_APP_SECRET",
                "version": "v1.0",
                "content_type": "JSON",
                "page_size": 100,
                "start_time_field": "startModifyTime",
                "end_time_field": "endModifyTime",
                "status_field": "orderStatusList",
                "status_values": [0, 1, 3, 4, 5, 6, 15],
                "extra_params": {},
                "page_index_base": 0,
            },
            "kingdee": {
                "enabled": False,
                "mode": "mock",
                "api_url": "",
                "token_env": "KINGDEE_TOKEN",
                "timeout_seconds": 30,
                "tracking_id_fields": [
                    "tracking_id",
                    "trackingId",
                    "id",
                    "bill_no",
                    "billNo",
                    "number",
                ],
                "extra_headers": {},
            },
            "rules": {
                "excluded_warehouses_enabled": False,
                "excluded_warehouses": [],
                "excluded_skus_enabled": False,
                "excluded_skus": [],
                "restricted_regions_enabled": False,
                "restricted_regions": [],
                "sku_group_map_enabled": False,
                "sku_group_map": {},
            },
            "message": {
                "max_attempts": 3,
                "retry_interval_seconds": 0,
            },
            "output": {
                "order_file_dir": "outputs/order_files",
            },
        }
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(default_config_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            config = ConfigService().load(config_path)
        # === MODIFIED END ===

        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.task.name, "daily-direct-order")
        self.assertEqual(config.task.window_minutes, 240)
        # === MODIFIED START ===
        # 原因：配置新增固定时间调度设置。
        # 影响范围：默认配置加载测试。
        self.assertFalse(config.schedule.enabled)
        self.assertEqual(config.schedule.run_at, "09:00")
        self.assertEqual(config.schedule.check_interval_seconds, 60)
        # === MODIFIED START ===
        # 原因：定时任务配置从单条升级为多条，默认配置需兼容为一条 default。
        # 影响范围：默认配置加载测试。
        self.assertEqual(len(config.schedules), 1)
        self.assertEqual(config.schedules[0].schedule_id, "default")
        self.assertEqual(config.schedules[0].name, "默认定时任务")
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：默认配置新增订单来源和吉客云接口设置。
        # 影响范围：默认配置加载测试。
        self.assertEqual(config.source.mode, "jikeyun")
        self.assertEqual(config.jikeyun.api_url, "https://open.jackyun.com/open/openapi/do")
        self.assertEqual(config.jikeyun.app_key_env, "JIKEYUN_APPKEY")
        self.assertEqual(config.jikeyun.app_secret_env, "JIKEYUN_APP_SECRET")
        self.assertEqual(config.jikeyun.version, "v1.0")
        self.assertEqual(config.jikeyun.content_type, "JSON")
        self.assertEqual(config.jikeyun.page_size, 100)
        self.assertEqual(config.jikeyun.start_time_field, "startModifyTime")
        self.assertEqual(config.jikeyun.end_time_field, "endModifyTime")
        self.assertEqual(config.jikeyun.status_field, "orderStatusList")
        self.assertEqual(config.jikeyun.status_values, (0, 1, 3, 4, 5, 6, 15))
        self.assertEqual(config.jikeyun.extra_params, {})
        self.assertEqual(config.jikeyun.page_index_base, 0)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：默认配置新增金蝶采购申请提交设置。
        # 影响范围：默认配置加载测试。
        self.assertFalse(config.kingdee.enabled)
        self.assertEqual(config.kingdee.mode, "mock")
        self.assertEqual(config.kingdee.api_url, "")
        self.assertEqual(config.kingdee.token_env, "KINGDEE_TOKEN")
        self.assertEqual(config.kingdee.timeout_seconds, 30)
        self.assertEqual(config.kingdee.tracking_id_fields[0], "tracking_id")
        self.assertEqual(config.kingdee.extra_headers, {})
        # === MODIFIED END ===
        self.assertFalse(config.rules.excluded_warehouses_enabled)
        self.assertEqual(config.rules.excluded_warehouses, ())
        # === MODIFIED START ===
        # 原因：SKU 配置从启用白名单改为排除黑名单，并新增模块级开关。
        # 影响范围：默认配置加载测试。
        self.assertFalse(config.rules.excluded_skus_enabled)
        self.assertEqual(config.rules.excluded_skus, ())
        # === MODIFIED END ===
        self.assertFalse(config.rules.restricted_regions_enabled)
        self.assertEqual(config.rules.restricted_regions, ())
        self.assertFalse(config.rules.sku_group_map_enabled)
        self.assertEqual(config.rules.sku_group_map, {})
        self.assertEqual(config.message.max_attempts, 3)
        self.assertEqual(config.message.retry_interval_seconds, 0)
        self.assertEqual(config.output.order_file_dir, Path("outputs/order_files"))
        self.assertFalse(config.rpa.enabled)
        self.assertEqual(config.rpa.xlsx_path, Path("input") / "销售单查询.xlsx")

    def test_from_dict_parses_full_config(self) -> None:
        config = ConfigService().from_dict(
            {
                "task": {
                    "name": "direct-order",
                    "window_minutes": 60,
                },
                # === MODIFIED START ===
                # 原因：覆盖固定时间调度配置解析。
                # 影响范围：完整配置解析测试。
                "schedule": {
                    "enabled": True,
                    "run_at": "8:30",
                    "check_interval_seconds": 30,
                },
                "schedules": [
                    {
                        "schedule_id": "morning",
                        "name": "上午任务",
                        "enabled": True,
                        "run_at": "8:30",
                        "check_interval_seconds": 30,
                    },
                    {
                        "schedule_id": "afternoon",
                        "name": "下午任务",
                        "enabled": False,
                        "run_at": "13:00",
                    },
                ],
                # === MODIFIED END ===
                # === MODIFIED START ===
                # 原因：覆盖订单来源和吉客云配置解析。
                # 影响范围：完整配置解析测试。
                "source": {
                    "mode": "jikeyun",
                },
                "jikeyun": {
                    "api_url": "https://example.test/openapi",
                    "app_key_env": "APP_KEY_ENV",
                    "app_secret_env": "APP_SECRET_ENV",
                    "version": "v2.0",
                    "content_type": "JSON",
                    "page_size": 50,
                    "start_time_field": "startModifyTime",
                    "end_time_field": "endModifyTime",
                    "status_field": "orderStatusList",
                    "status_values": [0, 1, " 3 "],
                    "extra_params": {
                        "shopIds": ["S-001"],
                    },
                    "page_index_base": 0,
                },
                "rpa": {
                    "enabled": True,
                    "xlsx_path": "input/custom.xlsx",
                },
                # === MODIFIED END ===
                # === MODIFIED START ===
                # 原因：覆盖金蝶采购申请提交配置解析。
                # 影响范围：完整配置解析测试。
                "kingdee": {
                    "enabled": True,
                    "mode": "http",
                    "api_url": "https://kingdee.example.test/purchase",
                    "token_env": "KD_TOKEN",
                    "timeout_seconds": 15,
                    "tracking_id_fields": ["dataId", "billNo"],
                    "extra_headers": {
                        "X-App": "direct-order",
                    },
                },
                # === MODIFIED END ===
                "rules": {
                    "excluded_warehouses_enabled": True,
                    "excluded_warehouses": [" WH-001 "],
                    # === MODIFIED START ===
                    # 原因：SKU 规则实际是排除逻辑，并支持模块级开关。
                    # 影响范围：完整配置解析测试。
                    "excluded_skus_enabled": True,
                    "excluded_skus": [" SKU-EXCLUDE "],
                    # === MODIFIED END ===
                    "restricted_regions": [
                        {
                            "sku_code": " SKU-001 ",
                            "province": " 浙江省 ",
                            "city": " 杭州市 ",
                        }
                    ],
                    "restricted_regions_enabled": True,
                    "sku_group_map_enabled": True,
                    "sku_group_map": {
                        " SKU-001 ": " GROUP-A ",
                    },
                },
                "message": {
                    "max_attempts": 2,
                    "retry_interval_seconds": 1.5,
                },
                "output": {
                    "order_file_dir": "tmp/orders",
                },
            }
        )

        self.assertEqual(config.task.name, "direct-order")
        self.assertTrue(config.schedule.enabled)
        self.assertEqual(config.schedule.run_at, "08:30")
        self.assertEqual(config.schedule.check_interval_seconds, 30)
        # === MODIFIED START ===
        # 原因：完整配置解析需要覆盖多条定时任务配置，并以第一条兼容旧 schedule 字段。
        # 影响范围：完整配置解析测试。
        self.assertEqual(config.schedule.schedule_id, "morning")
        self.assertEqual(config.schedule.name, "上午任务")
        self.assertEqual(len(config.schedules), 2)
        self.assertEqual(config.schedules[1].schedule_id, "afternoon")
        self.assertEqual(config.schedules[1].name, "下午任务")
        self.assertEqual(config.schedules[1].check_interval_seconds, 60)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：断言订单来源和吉客云配置已解析。
        # 影响范围：完整配置解析测试。
        self.assertEqual(config.source.mode, "jikeyun")
        self.assertEqual(config.jikeyun.api_url, "https://example.test/openapi")
        self.assertEqual(config.jikeyun.app_key_env, "APP_KEY_ENV")
        self.assertEqual(config.jikeyun.app_secret_env, "APP_SECRET_ENV")
        self.assertEqual(config.jikeyun.version, "v2.0")
        self.assertEqual(config.jikeyun.content_type, "JSON")
        self.assertEqual(config.jikeyun.page_size, 50)
        self.assertEqual(config.jikeyun.start_time_field, "startModifyTime")
        self.assertEqual(config.jikeyun.end_time_field, "endModifyTime")
        self.assertEqual(config.jikeyun.status_field, "orderStatusList")
        self.assertEqual(config.jikeyun.status_values, (0, 1, "3"))
        self.assertEqual(config.jikeyun.extra_params, {"shopIds": ["S-001"]})
        self.assertEqual(config.jikeyun.page_index_base, 0)
        self.assertTrue(config.rpa.enabled)
        self.assertEqual(config.rpa.xlsx_path, Path("input/custom.xlsx"))
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：断言金蝶配置已解析。
        # 影响范围：完整配置解析测试。
        self.assertTrue(config.kingdee.enabled)
        self.assertEqual(config.kingdee.mode, "http")
        self.assertEqual(config.kingdee.api_url, "https://kingdee.example.test/purchase")
        self.assertEqual(config.kingdee.token_env, "KD_TOKEN")
        self.assertEqual(config.kingdee.timeout_seconds, 15)
        self.assertEqual(config.kingdee.tracking_id_fields, ("dataId", "billNo"))
        self.assertEqual(config.kingdee.extra_headers, {"X-App": "direct-order"})
        # === MODIFIED END ===
        self.assertTrue(config.rules.excluded_warehouses_enabled)
        self.assertEqual(config.rules.excluded_warehouses, ("WH-001",))
        # === MODIFIED START ===
        # 原因：断言 SKU 排除配置和模块级开关已解析。
        # 影响范围：完整配置解析测试。
        self.assertTrue(config.rules.excluded_skus_enabled)
        self.assertEqual(config.rules.excluded_skus, ("SKU-EXCLUDE",))
        # === MODIFIED END ===
        self.assertTrue(config.rules.restricted_regions_enabled)
        self.assertTrue(config.rules.sku_group_map_enabled)
        self.assertEqual(config.rules.restricted_regions[0].sku_code, "SKU-001")
        self.assertEqual(config.rules.restricted_regions[0].province, "浙江省")
        self.assertEqual(config.rules.restricted_regions[0].city, "杭州市")
        self.assertEqual(config.rules.sku_group_map, {"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile="")})
        self.assertEqual(config.message.max_attempts, 2)
        self.assertEqual(config.message.retry_interval_seconds, 1.5)
        self.assertEqual(config.output.order_file_dir, Path("tmp/orders"))

    def test_invalid_task_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "task.name"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "",
                        "window_minutes": 60,
                    },
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )

    # === MODIFIED START ===
    # 原因：固定时间调度配置需要校验 HH:MM 时间。
    # 影响范围：配置校验测试。
    def test_invalid_schedule_run_at_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "schedule.run_at"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "schedule": {
                        "enabled": True,
                        "run_at": "25:00",
                    },
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )

    def test_duplicate_schedule_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "schedules.schedule_id"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "schedules": [
                        {
                            "schedule_id": "daily",
                            "enabled": True,
                            "run_at": "09:00",
                        },
                        {
                            "schedule_id": "daily",
                            "enabled": False,
                            "run_at": "13:00",
                        },
                    ],
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：订单来源配置只能在 mock 和 jikeyun 之间切换。
    # 影响范围：配置校验测试。
    def test_invalid_source_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "source.mode"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "source": {
                        "mode": "erp",
                    },
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )

    def test_invalid_jikeyun_extra_params_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "jikeyun.extra_params"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "jikeyun": {
                        "extra_params": [],
                    },
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：金蝶 HTTP 模式必须配置接口地址。
    # 影响范围：配置校验测试。
    def test_kingdee_http_mode_requires_api_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "kingdee.api_url"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "kingdee": {
                        "enabled": True,
                        "mode": "http",
                    },
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )

    # === MODIFIED START ===
    # 原因：金蝶未启用时允许预留 http 模式但暂不配置地址。
    # 影响范围：金蝶配置校验。
    def test_disabled_kingdee_http_mode_allows_blank_api_url(self) -> None:
        config = ConfigService().from_dict(
            {
                "task": {
                    "name": "direct-order",
                    "window_minutes": 60,
                },
                "kingdee": {
                    "enabled": False,
                    "mode": "http",
                },
                "rules": {},
                "message": {
                    "max_attempts": 1,
                    "retry_interval_seconds": 0,
                },
                "output": {
                    "order_file_dir": "tmp/orders",
                },
            }
        )

        self.assertFalse(config.kingdee.enabled)
        self.assertEqual(config.kingdee.mode, "http")
        self.assertEqual(config.kingdee.api_url, "")
    # === MODIFIED END ===

    def test_invalid_kingdee_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "kingdee.mode"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "kingdee": {
                        "mode": "sdk",
                    },
                    "rules": {},
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )
    # === MODIFIED END ===

    def test_invalid_restricted_region_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "province"):
            ConfigService().from_dict(
                {
                    "task": {
                        "name": "direct-order",
                        "window_minutes": 60,
                    },
                    "rules": {
                        "restricted_regions": [
                            {
                                "sku_code": "SKU-001",
                                "province": "",
                            }
                        ],
                    },
                    "message": {
                        "max_attempts": 1,
                        "retry_interval_seconds": 0,
                    },
                    "output": {
                        "order_file_dir": "tmp/orders",
                    },
                }
            )
