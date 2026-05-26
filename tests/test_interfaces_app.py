import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from application.api_service import ApiService
from interfaces.app import create_app


class InterfacesAppTests(TestCase):
    """Tests HTTP endpoints delegate to application services."""

    # === MODIFIED START ===
    # 原因：新增配置写入与任务历史接口测试需要复用独立临时文件。
    # 影响范围：接口测试初始化。
    def setUp(self) -> None:
        self.config_path = write_demo_config()
        self.task_store_path = Path("tmp") / "test_interfaces_app" / "task_runs.json"
        if self.task_store_path.exists():
            self.task_store_path.unlink()
        # === MODIFIED START ===
        # 原因：任务运行会持久化异常订单，接口测试需要独立异常订单文件。
        # 影响范围：异常订单接口测试。
        self.exception_order_path = Path("tmp") / "test_interfaces_app" / "exception_orders.json"
        if self.exception_order_path.exists():
            self.exception_order_path.unlink()
        self.exception_export_dir = Path("tmp") / "test_interfaces_app" / "exception_exports"
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：正常推送订单明细下载接口需要独立存储和导出目录。
        # 影响范围：接口测试初始化。
        self.pushed_order_path = Path("tmp") / "test_interfaces_app" / "pushed_orders.json"
        if self.pushed_order_path.exists():
            self.pushed_order_path.unlink()
        self.pushed_export_dir = Path("tmp") / "test_interfaces_app" / "pushed_exports"
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：付款回执接口需要独立状态文件和回执目录。
        # 影响范围：付款追踪接口测试。
        self.payment_receipt_path = Path("tmp") / "test_interfaces_app" / "payment_receipts.json"
        if self.payment_receipt_path.exists():
            self.payment_receipt_path.unlink()
        self.payment_receipt_dir = Path("tmp") / "test_interfaces_app" / "payment_receipts"
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：Scheduler 接口需要独立状态文件，避免测试和本地预览互相影响。
        # 影响范围：调度器接口测试。
        self.scheduler_state_path = Path("tmp") / "test_interfaces_app" / "scheduler_state.json"
        if self.scheduler_state_path.exists():
            self.scheduler_state_path.unlink()
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：执行日志接口需要独立存储和导出目录。
        # 影响范围：接口测试初始化。
        self.execution_log_path = Path("tmp") / "test_interfaces_app" / "execution_logs.json"
        if self.execution_log_path.exists():
            self.execution_log_path.unlink()
        self.execution_log_export_dir = Path("tmp") / "test_interfaces_app" / "execution_log_exports"
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：mock-run 的金蝶提交阶段需要独立 SKU-供应商对照数据。
        # 影响范围：接口任务运行与供应商映射测试。
        self.supplier_mapping_path = write_supplier_mappings()
        # === MODIFIED END ===
        self.client = TestClient(
            create_app(
                ApiService(
                    config_path=self.config_path,
                    task_store_path=self.task_store_path,
                    # === MODIFIED START ===
                    # 原因：接口服务需要读取测试专用 SKU-供应商对照数据。
                    # 影响范围：接口测试服务初始化。
                    supplier_mapping_path=self.supplier_mapping_path,
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：接口服务需要使用测试专用异常订单存储。
                    # 影响范围：异常订单接口测试。
                    exception_order_path=self.exception_order_path,
                    exception_export_dir=self.exception_export_dir,
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：接口服务需要使用测试专用正常推送订单明细存储。
                    # 影响范围：任务下载接口测试。
                    pushed_order_path=self.pushed_order_path,
                    pushed_order_export_dir=self.pushed_export_dir,
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：接口服务需要使用测试专用付款回执存储。
                    # 影响范围：付款追踪接口测试。
                    payment_receipt_path=self.payment_receipt_path,
                    payment_receipt_dir=self.payment_receipt_dir,
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：接口服务需要使用测试专用 Scheduler 状态。
                    # 影响范围：调度器接口测试。
                    scheduler_state_path=self.scheduler_state_path,
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：接口服务需要使用测试专用执行日志存储。
                    # 影响范围：执行日志接口测试。
                    execution_log_path=self.execution_log_path,
                    execution_log_export_dir=self.execution_log_export_dir,
                    # === MODIFIED END ===
                )
            )
        )
    # === MODIFIED END ===

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_order_file_download_allows_xlsx(self) -> None:
        order_file_dir = Path("tmp") / "test_interfaces_app" / "order_files"
        order_file_dir.mkdir(parents=True, exist_ok=True)
        file_name = "GROUP-A_20260430110000.xlsx"
        (order_file_dir / file_name).write_bytes(b"xlsx-bytes")
        secret = "download-secret"
        sig = hmac.HMAC(
            secret.encode("utf-8"),
            file_name.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        with patch.dict(os.environ, {"DOWNLOAD_SECRET_KEY": secret}, clear=False):
            response = self.client.get(
                f"/order-files/download?filename={file_name}&sig={sig}"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response.headers["content-type"],
        )
        self.assertEqual(response.content, b"xlsx-bytes")

    # === MODIFIED START ===
    # 原因：后台管理入口需要在给定管理员密码后启用登录验证，避免未授权触发真实推送。
    # 影响范围：/app、/static 和后台 API 入口。
    def test_admin_login_redirects_app_when_unauthenticated(self) -> None:
        with patch.dict(os.environ, {"AI_DDTS_ADMIN_PASSWORD": "secret"}, clear=False):
            client = TestClient(create_app(ApiService(config_path=self.config_path)))

        response = client.get("/app", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=/app")

    def test_admin_login_redirects_root_when_unauthenticated(self) -> None:
        with patch.dict(os.environ, {"AI_DDTS_ADMIN_PASSWORD": "secret"}, clear=False):
            client = TestClient(create_app(ApiService(config_path=self.config_path)))

        response = client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=/app")

    def test_admin_login_redirects_app_slash_when_unauthenticated(self) -> None:
        with patch.dict(os.environ, {"AI_DDTS_ADMIN_PASSWORD": "secret"}, clear=False):
            client = TestClient(create_app(ApiService(config_path=self.config_path)))

        response = client.get("/app/", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?next=/app")

    def test_admin_login_sets_cookie_and_allows_app(self) -> None:
        with patch.dict(os.environ, {"AI_DDTS_ADMIN_PASSWORD": "secret"}, clear=False):
            client = TestClient(
                create_app(
                    ApiService(
                        config_path=self.config_path,
                        task_store_path=self.task_store_path,
                        supplier_mapping_path=self.supplier_mapping_path,
                        exception_order_path=self.exception_order_path,
                        pushed_order_path=self.pushed_order_path,
                        execution_log_path=self.execution_log_path,
                    )
                )
            )

        login_response = client.post(
            "/login",
            data={"username": "admin", "password": "secret", "next": "/app"},
            follow_redirects=False,
        )

        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(login_response.headers["location"], "/app")
        self.assertIn("ai_ddts_session=", login_response.headers["set-cookie"])

        app_response = client.get("/app")
        self.assertEqual(app_response.status_code, 200)
        self.assertIn("text/html", app_response.headers["content-type"])

    def test_admin_session_blocks_api_without_cookie(self) -> None:
        with patch.dict(os.environ, {"AI_DDTS_ADMIN_PASSWORD": "secret"}, clear=False):
            client = TestClient(create_app(ApiService(config_path=self.config_path)))

        response = client.post("/tasks/run")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required"})
        self.assertNotIn("www-authenticate", response.headers)

    def test_admin_session_allows_task_trigger_with_cookie(self) -> None:
        with patch.dict(os.environ, {"AI_DDTS_ADMIN_PASSWORD": "secret"}, clear=False):
            client = TestClient(
                create_app(
                    ApiService(
                        config_path=self.config_path,
                        task_store_path=self.task_store_path,
                        supplier_mapping_path=self.supplier_mapping_path,
                        exception_order_path=self.exception_order_path,
                        pushed_order_path=self.pushed_order_path,
                        execution_log_path=self.execution_log_path,
                    )
                )
            )

        login_response = client.post(
            "/login",
            data={"username": "admin", "password": "secret"},
            follow_redirects=False,
        )
        response = client.post("/tasks/run")

        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(response.status_code, 200)
        self.assertIn("push_status", response.json())
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：新增静态管理台入口，需要验证 /app 和静态资源可访问。
    # 影响范围：FastAPI 静态前端托管。
    def test_frontend_app_returns_static_html(self) -> None:
        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        # === MODIFIED START ===
        # 原因：本地预览页面需要禁用缓存，避免规则 tab 使用旧 app.js。
        # 影响范围：/app 静态入口测试。
        self.assertEqual(response.headers["cache-control"], "no-store")
        # === MODIFIED END ===
        self.assertIn("厂直订单推送中心", response.text)
        self.assertIn("/static/app.css", response.text)
        # === MODIFIED START ===
        # 原因：任务清单滚动样式更新后需要提升 CSS 版本，避免本地预览保留旧样式。
        # 影响范围：前端静态入口测试。
        self.assertIn("/static/app.css?v=20260511-cn-buttons", response.text)
        # === MODIFIED END ===
        self.assertIn("/static/app.js", response.text)
        self.assertIn("/static/app.js?v=20260511-cn-buttons", response.text)
        # === MODIFIED START ===
        # 原因：UI 可视按键和图标标识改为中文。
        # 影响范围：前端静态入口测试。
        self.assertIn('<div class="brand-mark">厂</div>', response.text)
        self.assertIn('<span class="nav-icon">台</span>', response.text)
        self.assertIn('<span class="nav-icon">任</span>', response.text)
        self.assertIn('<span class="nav-icon">规</span>', response.text)
        self.assertIn('<span class="nav-icon">志</span>', response.text)
        self.assertIn('<span class="nav-icon">款</span>', response.text)
        self.assertIn('<span class="upload-cloud">上传</span>', response.text)
        self.assertNotIn('<span class="upload-cloud">UP</span>', response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务概览和任务清单只保留任务批次作为每次运行的识别字段。
        # 影响范围：前端静态入口测试。
        self.assertIn('placeholder="任务批次 / 状态 / 说明"', response.text)
        self.assertNotIn("<th>任务名称</th>", response.text)
        self.assertNotIn("任务批次 / trace_id / SKU", response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：新增执行日志可视化页面。
        # 影响范围：前端静态入口测试。
        self.assertIn("执行日志", response.text)
        self.assertIn("logRows", response.text)
        # === MODIFIED START ===
        # 原因：执行日志展示改为按周期筛选，不再固定最近条数。
        # 影响范围：前端静态入口测试。
        self.assertIn("logPeriodFilter", response.text)
        self.assertIn("logStartInput", response.text)
        self.assertIn("logEndInput", response.text)
        # === MODIFIED START ===
        # 原因：自动筛选需要展示当前周期和结果数量。
        # 影响范围：执行日志筛选区静态入口。
        self.assertIn("logFilterStatus", response.text)
        self.assertIn("已自动筛选", response.text)
        # === MODIFIED END ===
        # === MODIFIED END ===
        self.assertIn("logStageFilter", response.text)
        self.assertIn("downloadLogsButton", response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：规则配置页扩展为 5 项联动，并新增多个规则模块开关。
        # 影响范围：前端静态入口测试。
        self.assertIn("SKU供应商对照", response.text)
        self.assertIn("模块启用", response.text)
        self.assertIn("excludedWarehousesEnabledInput", response.text)
        self.assertIn("restrictedRegionsEnabledInput", response.text)
        self.assertIn("skuGroupMapEnabledInput", response.text)
        self.assertIn("SKU（商品名称）", response.text)
        self.assertIn("订单数据里的“商品名称”", response.text)
        self.assertIn("启用推送金蝶", response.text)
        self.assertIn("kingdeeEnabledInput", response.text)
        # === MODIFIED START ===
        # 原因：SKU-供应商对照不再需要供应商编码，后续由 ERP 商品档案同步更新。
        # 影响范围：规则配置中心静态入口。
        self.assertIn("SKU 供应商对照：商品名称,供应商名称", response.text)
        self.assertIn("ERP 商品档案定时同步", response.text)
        self.assertNotIn("商品名称,供应商编码,供应商名称", response.text)
        # === MODIFIED END ===
        self.assertNotIn("立即执行", response.text)
        self.assertNotIn("规则结果模型", response.text)
        # === MODIFIED START ===
        # 原因：任务清单需要专用布局容器承载面板内纵向滚动。
        # 影响范围：前端静态入口测试。
        self.assertIn("task-list-panel", response.text)
        self.assertIn("task-list-table-wrap", response.text)
        self.assertIn("rule-config-panel", response.text)
        self.assertIn("rule-config-scroll", response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：规则配置中心保存按钮文案按产品要求简化为“保存”。
        # 影响范围：前端静态入口测试。
        self.assertIn('id="saveRulesButton">保存</button>', response.text)
        self.assertNotIn('id="saveRulesButton">保存规则</button>', response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：规则配置中心新增定时任务配置模块。
        # 影响范围：前端静态入口测试。
        self.assertIn("定时任务配置", response.text)
        self.assertIn("scheduleRows", response.text)
        # === MODIFIED START ===
        # 原因：工作台首页删除异常订单明细和流程概览，明细下载统一放到任务清单。
        # 影响范围：前端静态入口测试。
        self.assertNotIn("流程概览", response.text)
        self.assertNotIn("异常订单明细", response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：推送状态新增“部分推送”，前端筛选项需要展示。
        # 影响范围：任务清单静态入口。
        self.assertIn("部分推送", response.text)
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED END ===

    def test_frontend_static_assets_are_served(self) -> None:
        css_response = self.client.get("/static/app.css")
        js_response = self.client.get("/static/app.js")

        self.assertEqual(css_response.status_code, 200)
        self.assertIn("text/css", css_response.headers["content-type"])
        self.assertIn("javascript", js_response.headers["content-type"])
        # === MODIFIED START ===
        # 原因：静态资源需要显式禁用缓存，确保规则 tab 联动脚本及时生效。
        # 影响范围：静态资源测试。
        self.assertEqual(css_response.headers["cache-control"], "no-store")
        self.assertEqual(js_response.headers["cache-control"], "no-store")
        # === MODIFIED END ===
        self.assertIn("loadApp", js_response.text)
        # === MODIFIED START ===
        # 原因：前端 JS/CSS 需要包含 5 项联动面板和排除 SKU 开关逻辑。
        # 影响范围：静态资源测试。
        self.assertIn("setRuleTab", js_response.text)
        # === MODIFIED START ===
        # 原因：执行日志页面需要前端拉取、渲染和下载执行日志。
        # 影响范围：静态资源测试。
        self.assertIn("buildExecutionLogQuery", js_response.text)
        self.assertIn("refreshExecutionLogs", js_response.text)
        self.assertIn("start_at", js_response.text)
        self.assertIn("end_at", js_response.text)
        self.assertIn("renderExecutionLogs", js_response.text)
        self.assertIn("downloadExecutionLogs", js_response.text)
        self.assertIn("groupExecutionLogs", js_response.text)
        self.assertIn("updateExecutionLogFilterStatus", js_response.text)
        # === MODIFIED START ===
        # 原因：工作台任务概览删除内部任务类型列后，空态 colspan 需要同步减少。
        # 影响范围：前端静态资源测试。
        self.assertIn("renderDashboardTasks", js_response.text)
        self.assertIn("    6,", js_response.text)
        # === MODIFIED END ===
        self.assertIn("log-list-panel", css_response.text)
        self.assertIn("log-filter-status", css_response.text)
        self.assertIn("log-timeline-wrap", css_response.text)
        self.assertIn(".log-group", css_response.text)
        self.assertIn(".log-step-meta", css_response.text)
        # === MODIFIED END ===
        self.assertIn("excluded_warehouses_enabled", js_response.text)
        self.assertIn("excluded_skus_enabled", js_response.text)
        self.assertIn("restricted_regions_enabled", js_response.text)
        self.assertIn("sku_group_map_enabled", js_response.text)
        self.assertIn("kingdeeEnabledInput", js_response.text)
        self.assertIn("collectScheduleRows", js_response.text)
        self.assertIn("addScheduleRow", js_response.text)
        self.assertIn("rule-panel", css_response.text)
        self.assertIn("rule-schedule-table", css_response.text)
        # === MODIFIED START ===
        # 原因：规则配置内容较长时需要在面板内部滚动，避免超过当前页面。
        # 影响范围：前端静态资源测试。
        self.assertIn("#view-rules.is-active", css_response.text)
        self.assertIn("rule-config-panel", css_response.text)
        self.assertIn("rule-config-scroll", css_response.text)
        self.assertIn("height: calc(100vh - 154px)", css_response.text)
        self.assertIn("height: calc(100vh - 220px)", css_response.text)
        self.assertIn("overflow-y: scroll", css_response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务清单多条记录时需要在当前页面内滚动，右侧详情抽屉也不能超过视口。
        # 影响范围：前端静态资源测试。
        self.assertIn("task-list-panel", css_response.text)
        self.assertIn("task-list-table-wrap", css_response.text)
        self.assertIn("max-height: calc(100vh - 142px)", css_response.text)
        self.assertIn("scrollbar-gutter: stable", css_response.text)
        self.assertIn("max-height: 100dvh", css_response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：顶部菜单按钮只服务移动端侧边栏，桌面端不应显示无效入口。
        # 影响范围：前端静态资源测试。
        self.assertIn("display: none", css_response.text)
        self.assertIn("display: inline-flex", css_response.text)
        self.assertIn("body.menu-open .sidebar", css_response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：工作台首页删除异常订单明细和流程概览，不再保留下方展示模块。
        # 影响范围：前端静态资源测试。
        self.assertNotIn("/exception-orders?limit=10", js_response.text)
        self.assertNotIn("renderExceptions", js_response.text)
        self.assertNotIn("flow-only-grid", css_response.text)
        self.assertNotIn("flow-map", css_response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：任务清单下载需要区分异常订单和正常推送订单明细。
        # 影响范围：前端静态资源测试。
        self.assertIn("pushed-orders/download", js_response.text)
        self.assertIn("异常订单", js_response.text)
        self.assertIn("正常推送订单", js_response.text)
        self.assertIn("startTaskDownload", js_response.text)
        self.assertIn("triggerDownload", js_response.text)
        self.assertIn("正在下载异常订单", js_response.text)
        self.assertIn("data-action=\"download-exceptions\"", js_response.text)
        # === MODIFIED START ===
        # 原因：没有对应明细时下载入口应禁用，避免用户点出空 CSV 后误认为按钮无效。
        # 影响范围：任务行操作按钮。
        self.assertIn("action-disabled", js_response.text)
        self.assertIn("当前任务没有正常推送订单", js_response.text)
        self.assertIn("action-disabled", css_response.text)
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：工作台指标角标统一中文化。
        # 影响范围：前端静态资源测试。
        self.assertIn('mark: "订"', js_response.text)
        self.assertIn('mark: "推"', js_response.text)
        self.assertIn('mark: "异"', js_response.text)
        self.assertIn('mark: "款"', js_response.text)
        self.assertNotIn('mark: "OD"', js_response.text)
        self.assertNotIn('mark: "OK"', js_response.text)
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：部分推送状态需要在前端按提醒色展示。
        # 影响范围：前端静态资源测试。
        self.assertIn('"部分推送"', js_response.text)
        # === MODIFIED END ===
        # === MODIFIED END ===
    # === MODIFIED END ===

    def test_config_returns_current_config(self) -> None:
        response = self.client.get("/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task"]["name"], "daily-direct-order")
        self.assertEqual(payload["rules"]["sku_group_map"], {"SKU-PASS": {"group_name": "GROUP-A", "owner_mobile": "", "user_id": ""}})
        # === MODIFIED START ===
        # 原因：配置接口需要返回规则模块级开关。
        # 影响范围：/config。
        self.assertTrue(payload["rules"]["excluded_warehouses_enabled"])
        self.assertFalse(payload["rules"]["excluded_skus_enabled"])
        self.assertFalse(payload["rules"]["restricted_regions_enabled"])
        self.assertTrue(payload["rules"]["sku_group_map_enabled"])
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：配置接口需要返回金蝶采购申请提交设置。
        # 影响范围：/config。
        self.assertFalse(payload["kingdee"]["enabled"])
        self.assertEqual(payload["kingdee"]["mode"], "mock")
        self.assertEqual(payload["kingdee"]["token_env"], "KINGDEE_TOKEN")
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：配置接口需要返回多条定时任务配置，旧单条配置兼容为 default。
        # 影响范围：/config。
        self.assertEqual(payload["schedules"][0]["schedule_id"], "default")
        self.assertEqual(payload["schedules"][0]["name"], "默认定时任务")
        # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：覆盖完整配置替换接口，确保 API 委托应用层保存配置。
    # 影响范围：/config 写入接口测试。
    def test_replace_config_persists_current_config(self) -> None:
        payload = {
            "task": {
                "name": "direct-order-updated",
                "window_minutes": 60,
            },
            "rules": {
                # === MODIFIED START ===
                # 原因：完整配置替换需要持久化规则模块级启用状态。
                # 影响范围：/config 写入接口测试。
                "excluded_warehouses_enabled": False,
                # === MODIFIED END ===
                "excluded_warehouses": ["WH-IGNORE", "WH-NEW"],
                # === MODIFIED START ===
                # 原因：SKU 规则从启用白名单改为排除黑名单，并新增模块级开关。
                # 影响范围：完整配置替换接口测试。
                "excluded_skus_enabled": True,
                "excluded_skus": ["SKU-EXCLUDE", "SKU-NEW"],
                # === MODIFIED END ===
                "restricted_regions": [
                    {
                        "sku_code": "SKU-NEW",
                        "province": "Zhejiang",
                        "city": "Hangzhou",
                        "district": None,
                    }
                ],
                # === MODIFIED START ===
                # 原因：完整配置替换需要持久化限发区域和 SKU 群配置模块开关。
                # 影响范围：/config 写入接口测试。
                "restricted_regions_enabled": True,
                "sku_group_map_enabled": True,
                # === MODIFIED END ===
                "sku_group_map": {
                    "SKU-PASS": "GROUP-A",
                    "SKU-NEW": "GROUP-B",
                },
            },
            "message": {
                "max_attempts": 3,
                "retry_interval_seconds": 0,
            },
            # === MODIFIED START ===
            # 原因：完整配置替换需要支持多条定时任务配置。
            # 影响范围：/config 写入接口测试。
            "schedules": [
                {
                    "schedule_id": "morning",
                    "name": "上午任务",
                    "enabled": True,
                    "run_at": "08:30",
                    "check_interval_seconds": 30,
                },
                {
                    "schedule_id": "afternoon",
                    "name": "下午任务",
                    "enabled": False,
                    "run_at": "13:00",
                    "check_interval_seconds": 60,
                },
            ],
            # === MODIFIED END ===
            "output": {
                "order_file_dir": "tmp/test_interfaces_app/order_files_updated",
            },
        }

        response = self.client.put("/config", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["name"], "direct-order-updated")
        self.assertFalse(response.json()["rules"]["excluded_warehouses_enabled"])
        self.assertTrue(response.json()["rules"]["excluded_skus_enabled"])
        self.assertTrue(response.json()["rules"]["restricted_regions_enabled"])
        self.assertTrue(response.json()["rules"]["sku_group_map_enabled"])
        self.assertEqual(response.json()["schedules"][0]["schedule_id"], "morning")
        self.assertEqual(response.json()["schedule"]["schedule_id"], "morning")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["rules"]["excluded_warehouses_enabled"])
        self.assertEqual(persisted["rules"]["sku_group_map"]["SKU-NEW"], {"group_name": "GROUP-B", "owner_mobile": "", "user_id": ""})
        self.assertTrue(persisted["rules"]["sku_group_map_enabled"])
        self.assertEqual(persisted["schedules"][1]["schedule_id"], "afternoon")

    def test_update_rule_config_persists_partial_update(self) -> None:
        response = self.client.put(
            "/config/rules",
            json={
                # === MODIFIED START ===
                # 原因：局部规则更新需要支持新规则模块开关。
                # 影响范围：/config/rules 测试。
                "excluded_warehouses_enabled": False,
                "restricted_regions_enabled": True,
                "sku_group_map_enabled": True,
                # === MODIFIED END ===
                # === MODIFIED START ===
                # 原因：局部规则更新改写排除 SKU 字段和模块级开关。
                # 影响范围：/config/rules 测试。
                "excluded_skus_enabled": True,
                "excluded_skus": ["SKU-EXCLUDE", "SKU-NEW"],
                # === MODIFIED END ===
                "sku_group_map": {
                    "SKU-PASS": "GROUP-A",
                    "SKU-NEW": "GROUP-B",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["rules"]["excluded_warehouses_enabled"])
        self.assertTrue(payload["rules"]["excluded_skus_enabled"])
        self.assertTrue(payload["rules"]["restricted_regions_enabled"])
        self.assertTrue(payload["rules"]["sku_group_map_enabled"])
        self.assertEqual(payload["rules"]["excluded_skus"], ["SKU-EXCLUDE", "SKU-NEW"])
        self.assertEqual(payload["rules"]["sku_group_map"]["SKU-NEW"], {"group_name": "GROUP-B", "owner_mobile": "", "user_id": ""})
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["rules"]["excluded_warehouses_enabled"])
        self.assertTrue(persisted["rules"]["excluded_skus_enabled"])
        self.assertTrue(persisted["rules"]["restricted_regions_enabled"])
        self.assertTrue(persisted["rules"]["sku_group_map_enabled"])
        self.assertEqual(persisted["rules"]["sku_group_map"]["SKU-NEW"], {"group_name": "GROUP-B", "owner_mobile": "", "user_id": ""})

    # === MODIFIED START ===
    # 原因：SKU 群导入更新群名/手机号时不能丢弃已有 user_id，否则手机号解析兜底会表现为配置不生效。
    # 影响范围：SKU 群 XLSX 导入接口与真实推送配置。
    def test_upload_sku_group_xlsx_preserves_existing_user_id(self) -> None:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["rules"]["sku_group_map"] = {
            "SKU-PASS": {
                "group_name": "GROUP-A",
                "owner_mobile": "15176152071",
                "user_id": "USER-EXISTING",
            }
        }
        self.config_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with patch(
            "application.api_service.load_sku_groups_from_bytes",
            return_value=[
                {
                    "sku_code": "SKU-PASS",
                    "group_name": "GROUP-B",
                    "owner_mobile": "15176152071",
                }
            ],
        ):
            response = self.client.post(
                "/config/sku-groups/upload-xlsx",
                files={
                    "file": (
                        "sku-groups.xlsx",
                        b"placeholder",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted["rules"]["sku_group_map"]["SKU-PASS"],
            {
                "group_name": "GROUP-B",
                "owner_mobile": "15176152071",
                "user_id": "USER-EXISTING",
            },
        )
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：SKU 群配置同步 URL 为空时必须可观测地跳过，不能静默失败或误请求远端。
    # 影响范围：/config/sku-groups/sync-caller-configs 与执行日志。
    def test_sync_sku_group_caller_configs_skips_when_url_missing(self) -> None:
        response = self.client.post("/config/sku-groups/sync-caller-configs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["reason"], "product_caller_sync.api_url is empty")
        logs = json.loads(self.execution_log_path.read_text(encoding="utf-8"))
        self.assertEqual(logs[-1]["result"], "跳过")
        self.assertIn("SKU群推送配置同步跳过", logs[-1]["summary"])

    # 原因：前端按钮触发的同步接口需要解析手机号、POST 远端，并把远端返回体写回响应和执行日志。
    # 影响范围：/config/sku-groups/sync-caller-configs。
    def test_sync_sku_group_caller_configs_posts_payload_and_logs_result(self) -> None:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["product_caller_sync"] = {
            "api_url": "https://push-center.example.test/sync",
            "timeout_seconds": 7,
        }
        data["rules"]["sku_group_map"] = {
            "三只松鼠核桃": {
                "group_name": "三只松鼠对接群",
                "owner_mobile": "15176152071",
                "user_id": "",
            },
            "雪中飞衣服": {
                "group_name": "雪中飞产品对接群",
                "owner_mobile": "15176152072",
                "user_id": "",
            },
        }
        self.config_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        captured: dict[str, object] = {}

        def fake_userid_urlopen(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            return _JsonResponse({"userid": f"owner{body['mobile'][-3:]}"})

        def fake_sync_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _JsonResponse(
                {
                    "code": 200,
                    "data_id": captured["body"]["data_id"],
                    "synced": 2,
                    "created": 2,
                    "updated": 0,
                    "skipped": 0,
                }
            )

        client = TestClient(
            create_app(
                ApiService(
                    config_path=self.config_path,
                    task_store_path=self.task_store_path,
                    supplier_mapping_path=self.supplier_mapping_path,
                    exception_order_path=self.exception_order_path,
                    pushed_order_path=self.pushed_order_path,
                    execution_log_path=self.execution_log_path,
                    userid_urlopen=fake_userid_urlopen,
                    product_caller_sync_urlopen=fake_sync_urlopen,
                )
            )
        )

        response = client.post("/config/sku-groups/sync-caller-configs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["remote_response"]["synced"], 2)
        self.assertEqual(captured["url"], "https://push-center.example.test/sync")
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(captured["body"]["count"], 2)
        self.assertEqual(
            captured["body"]["data"],
            [
                {
                    "goods_name": "三只松鼠核桃",
                    "group_name": "三只松鼠对接群",
                    "user_id": "owner071",
                },
                {
                    "goods_name": "雪中飞衣服",
                    "group_name": "雪中飞产品对接群",
                    "user_id": "owner072",
                },
            ],
        )
        logs = json.loads(self.execution_log_path.read_text(encoding="utf-8"))
        self.assertEqual(logs[-1]["result"], "成功")
        self.assertEqual(logs[-1]["details"]["remote_response"]["synced"], 2)

    # 原因：SKU 群 Excel 上传保存后要异步触发同一套推送人配置同步。
    # 影响范围：/config/sku-groups/upload-xlsx。
    def test_upload_sku_group_xlsx_triggers_caller_config_sync(self) -> None:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["product_caller_sync"] = {
            "api_url": "https://push-center.example.test/sync",
            "timeout_seconds": 7,
        }
        self.config_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        captured: dict[str, object] = {}

        def fake_userid_urlopen(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            return _JsonResponse({"userid": f"owner{body['mobile'][-3:]}"})

        def fake_sync_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _JsonResponse(
                {
                    "code": 200,
                    "data_id": captured["body"]["data_id"],
                    "synced": 1,
                    "created": 1,
                    "updated": 0,
                    "skipped": 0,
                }
            )

        client = TestClient(
            create_app(
                ApiService(
                    config_path=self.config_path,
                    task_store_path=self.task_store_path,
                    supplier_mapping_path=self.supplier_mapping_path,
                    exception_order_path=self.exception_order_path,
                    pushed_order_path=self.pushed_order_path,
                    execution_log_path=self.execution_log_path,
                    userid_urlopen=fake_userid_urlopen,
                    product_caller_sync_urlopen=fake_sync_urlopen,
                )
            )
        )

        with patch(
            "application.api_service.load_sku_groups_from_bytes",
            return_value=[
                {
                    "sku_code": "三只松鼠核桃",
                    "group_name": "三只松鼠对接群",
                    "owner_mobile": "15176152071",
                }
            ],
        ):
            response = client.post(
                "/config/sku-groups/upload-xlsx",
                files={
                    "file": (
                        "sku-groups.xlsx",
                        b"placeholder",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        deadline = time.time() + 2
        while "body" not in captured and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(
            captured["body"]["data"],
            [
                {
                    "goods_name": "三只松鼠核桃",
                    "group_name": "三只松鼠对接群",
                    "user_id": "owner071",
                }
            ],
        )
    # === MODIFIED END ===

    def test_update_rule_config_rejects_unknown_key(self) -> None:
        response = self.client.put("/config/rules", json={"unknown": []})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported rule config keys", response.json()["detail"])
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：新增 ERP SKU-供应商对照数据查询和批量覆盖接口。
    # 影响范围：/supplier-mappings。
    def test_supplier_mappings_returns_current_items(self) -> None:
        response = self.client.get("/supplier-mappings")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["sku_code"], "SKU-PASS")
        self.assertEqual(payload["items"][0]["supplier_name"], "Supplier A")
        self.assertNotIn("supplier_code", payload["items"][0])

    def test_replace_supplier_mappings_persists_items(self) -> None:
        response = self.client.put(
            "/supplier-mappings",
            json={
                "items": [
                    {
                        "sku_code": "SKU-NEW",
                        "supplier_name": "Supplier New",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["sku_code"], "SKU-NEW")
        persisted = json.loads(self.supplier_mapping_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["items"][0]["supplier_name"], "Supplier New")
        self.assertNotIn("supplier_code", persisted["items"][0])

    def test_replace_supplier_mappings_rejects_invalid_payload(self) -> None:
        response = self.client.put("/supplier-mappings", json={"items": {}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("items must be a list", response.json()["detail"])
    # === MODIFIED END ===

    def test_latest_task_returns_404_before_run(self) -> None:
        response = self.client.get("/tasks/latest")

        self.assertEqual(response.status_code, 404)

    def test_mock_run_then_latest_task(self) -> None:
        run_response = self.client.post("/tasks/mock-run")

        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertEqual(run_payload["passed_count"], 1)
        self.assertEqual(run_payload["ignored_count"], 1)
        self.assertEqual(run_payload["error_count"], 1)
        self.assertEqual(run_payload["delivery_count"], 1)
        # === MODIFIED START ===
        # 原因：任务接口需要返回完整状态追踪字段。
        # 影响范围：/tasks/mock-run 和 /tasks/latest。
        self.assertEqual(run_payload["push_status"], "已推送")
        self.assertEqual(run_payload["kingdee_status"], "未启用")
        self.assertIsNone(run_payload["kingdee_tracking_id"])
        self.assertEqual(run_payload["task_name"], "daily-direct-order")
        self.assertIsNone(run_payload["failure_stage"])
        self.assertIsNone(run_payload["failure_reason"])
        self.assertIn("created_at", run_payload)
        self.assertIn("window_start", run_payload)
        self.assertIn("window_end", run_payload)
        # === MODIFIED END ===

        latest_response = self.client.get("/tasks/latest")
        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(latest_response.json(), run_payload)
        self.assertEqual(latest_response.json()["payment_status"], "未付款")

    # === MODIFIED START ===
    # 原因：任务来源已配置化，新增正式任务运行入口。
    # 影响范围：/tasks/run。
    def test_run_task_endpoint_then_latest_task(self) -> None:
        run_response = self.client.post("/tasks/run")

        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertEqual(run_payload["passed_count"], 1)
        self.assertEqual(run_payload["ignored_count"], 1)
        self.assertEqual(run_payload["error_count"], 1)
        # === MODIFIED START ===
        # 原因：正式任务运行入口同样需要返回状态追踪字段。
        # 影响范围：/tasks/run。
        self.assertEqual(run_payload["push_status"], "已推送")
        self.assertEqual(run_payload["kingdee_status"], "未启用")
        # === MODIFIED END ===

        latest_response = self.client.get("/tasks/latest")
        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(latest_response.json(), run_payload)
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：覆盖任务运行历史持久化查询接口。
    # 影响范围：/tasks/history。
    def test_mock_run_persists_task_history(self) -> None:
        first_response = self.client.post("/tasks/mock-run")
        second_response = self.client.post("/tasks/mock-run")

        history_response = self.client.get("/tasks/history?limit=2")

        self.assertEqual(history_response.status_code, 200)
        # === MODIFIED START ===
        # 原因：任务批次编码改为当天日期 + 四位数累计，API 连续运行需递增。
        # 影响范围：tasks/mock-run 与 tasks/history。
        today_prefix = datetime.now().strftime("%Y%m%d")
        self.assertEqual(first_response.json()["trace_id"], f"{today_prefix}0001")
        self.assertEqual(second_response.json()["trace_id"], f"{today_prefix}0002")
        # === MODIFIED END ===
        history_payload = history_response.json()
        self.assertEqual(history_payload[0], second_response.json())
        self.assertEqual(history_payload[1], first_response.json())

    def test_task_history_rejects_invalid_limit(self) -> None:
        response = self.client.get("/tasks/history?limit=0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.json()["detail"])
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：新增付款状态查询和付款回执上传接口。
    # 影响范围：/tasks/{trace_id}/payment 和 /tasks/{trace_id}/payment-receipt。
    def test_payment_status_defaults_unpaid(self) -> None:
        response = self.client.get("/tasks/TRACE-001/payment")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["trace_id"], "TRACE-001")
        self.assertEqual(payload["payment_status"], "未付款")
        self.assertIsNone(payload["receipt_file_path"])

    def test_upload_payment_receipt_marks_task_paid(self) -> None:
        run_response = self.client.post("/tasks/mock-run")
        trace_id = run_response.json()["trace_id"]

        upload_response = self.client.post(
            f"/tasks/{trace_id}/payment-receipt",
            files={"file": ("receipt.png", b"receipt-bytes", "image/png")},
        )

        self.assertEqual(upload_response.status_code, 200)
        upload_payload = upload_response.json()
        self.assertEqual(upload_payload["payment_status"], "已付款")
        self.assertEqual(upload_payload["original_filename"], "receipt.png")
        self.assertTrue(Path(upload_payload["receipt_file_path"]).exists())

        status_response = self.client.get(f"/tasks/{trace_id}/payment")
        self.assertEqual(status_response.json()["payment_status"], "已付款")

        latest_response = self.client.get("/tasks/latest")
        self.assertEqual(latest_response.json()["payment_status"], "已付款")

    def test_upload_payment_receipt_rejects_empty_file(self) -> None:
        response = self.client.post(
            "/tasks/TRACE-001/payment-receipt",
            files={"file": ("receipt.png", b"", "image/png")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must not be empty", response.json()["detail"])
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：新增异常订单查询和下载接口。
    # 影响范围：/exception-orders 和 /exception-orders/download。
    def test_mock_run_persists_exception_orders(self) -> None:
        self.client.post("/tasks/mock-run")

        response = self.client.get("/exception-orders")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["order_no"], "SO-LOCAL-ERROR")
        self.assertEqual(payload["items"][0]["sku_code"], "SKU-NO-GROUP")
        # === MODIFIED START ===
        # 原因：异常订单接口需要带出抓单仓库字段。
        # 影响范围：/exception-orders。
        self.assertEqual(payload["items"][0]["warehouse_name"], "WH-LOCAL")
        # === MODIFIED END ===
        self.assertEqual(payload["items"][0]["reason"], "未配置推送群")

    def test_exception_orders_download_returns_csv(self) -> None:
        run_response = self.client.post("/tasks/mock-run")
        trace_id = run_response.json()["trace_id"]

        response = self.client.get(f"/exception-orders/download?trace_id={trace_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("SO-LOCAL-ERROR", response.text)
        self.assertIn("供应商名称", response.text)
        self.assertNotIn("供应商编码", response.text)

    # === MODIFIED START ===
    # 原因：任务清单需要下载当前批次正常推送订单明细，并包含供应商字段。
    # 影响范围：/tasks/{trace_id}/pushed-orders/download。
    def test_pushed_orders_download_returns_supplier_enriched_csv(self) -> None:
        run_response = self.client.post("/tasks/mock-run")
        trace_id = run_response.json()["trace_id"]

        response = self.client.get(f"/tasks/{trace_id}/pushed-orders/download")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("供应商名称", response.text)
        self.assertNotIn("供应商编码", response.text)
        self.assertIn("Supplier A", response.text)
        self.assertIn("SO-LOCAL-PASS", response.text)
        self.assertNotIn("SO-LOCAL-ERROR", response.text)
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：新增执行日志查询和下载接口。
    # 影响范围：/execution-logs 和 /execution-logs/download。
    def test_mock_run_persists_execution_logs(self) -> None:
        run_response = self.client.post("/tasks/mock-run")
        trace_id = run_response.json()["trace_id"]

        response = self.client.get(f"/execution-logs?trace_id={trace_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["trace_id"], trace_id)
        self.assertIn("任务执行完成", [item["summary"] for item in payload["items"]])
        self.assertEqual(
            {item["stage"] for item in payload["items"]},
            {"任务", "抓单", "规则判断", "生成文件", "推送群", "金蝶"},
        )

    # === MODIFIED START ===
    # 原因：执行日志页面改为周期查询，接口需要支持 start_at/end_at。
    # 影响范围：/execution-logs。
    def test_execution_logs_can_filter_by_time_range(self) -> None:
        self.client.post("/tasks/mock-run")

        response = self.client.get("/execution-logs?start_at=2999-01-01T00:00:00")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
    # === MODIFIED END ===

    def test_execution_logs_download_returns_csv(self) -> None:
        run_response = self.client.post("/tasks/mock-run")
        trace_id = run_response.json()["trace_id"]

        response = self.client.get(
            f"/execution-logs/download?trace_id={trace_id}&stage=任务&start_at=2020-01-01T00:00:00"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("创建时间", response.text)
        self.assertIn(trace_id, response.text)
        self.assertIn("任务执行完成", response.text)

    def test_execution_logs_rejects_invalid_limit(self) -> None:
        response = self.client.get("/execution-logs?limit=0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.json()["detail"])
    # === MODIFIED END ===

    def test_exception_orders_rejects_invalid_limit(self) -> None:
        response = self.client.get("/exception-orders?limit=0")

        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.json()["detail"])
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：新增固定时间 Scheduler 状态和 tick 接口。
    # 影响范围：/scheduler/status 和 /scheduler/tick。
    def test_scheduler_status_returns_default_disabled_config(self) -> None:
        response = self.client.get("/scheduler/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["run_at"], "09:00")
        self.assertFalse(payload["due"])
        # === MODIFIED START ===
        # 原因：调度器状态接口需要兼容旧字段并返回多条配置明细。
        # 影响范围：/scheduler/status。
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["schedule_id"], "default")
        self.assertEqual(payload["enabled_count"], 0)
        # === MODIFIED END ===

    def test_scheduler_tick_returns_disabled_when_not_enabled(self) -> None:
        response = self.client.post("/scheduler/tick")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "未启用")
        self.assertFalse(payload["should_run"])

    def test_scheduler_loop_status_returns_background_state(self) -> None:
        response = self.client.get("/scheduler/loop/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("running", payload)
        self.assertEqual(payload["interval_seconds"], 60)
        self.assertEqual(payload["scheduler"]["run_at"], "09:00")
        self.assertEqual(payload["scheduler"]["items"][0]["schedule_id"], "default")
    # === MODIFIED END ===


def write_demo_config() -> Path:
    """Writes a deterministic config file for API tests."""

    config_path = Path("tmp") / "test_interfaces_app" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "task": {
                    "name": "daily-direct-order",
                    "window_minutes": 240,
                },
                # === MODIFIED START ===
                # 原因：金蝶推送当前默认不启用。
                # 影响范围：接口任务运行测试配置。
                "kingdee": {
                    "enabled": False,
                    "mode": "mock",
                    "api_url": "",
                    "token_env": "KINGDEE_TOKEN",
                    "timeout_seconds": 30,
                    "tracking_id_fields": ["tracking_id", "trackingId", "id", "bill_no", "billNo", "number"],
                    "extra_headers": {},
                },
                # === MODIFIED END ===
                # === MODIFIED START ===
                # 原因：默认接口测试覆盖固定时间调度配置。
                # 影响范围：接口测试配置。
                "schedule": {
                    "enabled": False,
                    "run_at": "09:00",
                    "check_interval_seconds": 60,
                },
                # === MODIFIED END ===
                "rules": {
                    # === MODIFIED START ===
                    # 原因：接口测试配置显式声明规则模块开关，避免旧配置兼容默认值掩盖字段缺失。
                    # 影响范围：接口测试配置。
                    "excluded_warehouses_enabled": True,
                    # === MODIFIED END ===
                    "excluded_warehouses": ["WH-IGNORE"],
                    # === MODIFIED START ===
                    # 原因：接口测试配置改用 SKU 排除字段，并默认关闭排除模块。
                    # 影响范围：mock-run 规则配置。
                    "excluded_skus_enabled": False,
                    "excluded_skus": [],
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：接口测试配置显式声明限发区域和 SKU 群配置模块开关。
                    # 影响范围：接口测试配置。
                    "restricted_regions_enabled": False,
                    # === MODIFIED END ===
                    "restricted_regions": [],
                    # === MODIFIED START ===
                    # 原因：接口测试的通过订单仍需按 SKU 群配置拆分推送。
                    # 影响范围：mock-run 规则配置。
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
                    "order_file_dir": "tmp/test_interfaces_app/order_files",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path


# === MODIFIED START ===
# 原因：为接口 mock-run 和供应商映射接口准备测试用 ERP 同步数据。
# 影响范围：接口测试数据。
def write_supplier_mappings() -> Path:
    """Writes deterministic supplier mappings for API tests."""

    mapping_path = Path("tmp") / "test_interfaces_app" / "sku_supplier_mappings.json"
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


# === MODIFIED START ===
# 原因：SKU 群推送人配置同步测试需要替代 urllib 响应，避免访问真实外部接口。
# 影响范围：接口层同步测试。
class _JsonResponse:
    """Minimal urllib response double returning a JSON payload."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def close(self) -> None:
        return None
# === MODIFIED END ===
