from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlencode

# === MODIFIED START ===
# 原因：配置接口需要把应用层校验错误转换为 HTTP 400 响应。
# 影响范围：接口层错误响应映射。
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
# === MODIFIED END ===

from application.api_service import ApiService
from application.config_service import ConfigService
from infrastructure.xlsx_region_parser import ImportRuleError
from shared.env import get_env, load_dotenv, resolve_config_path

# === MODIFIED START ===
# 原因：推送/上传订单文件统一改为 Excel，下载接口需要返回 Excel MIME。
# 影响范围：/order-files/download。
EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：限发区域和 SKU 群配置的确认导入接口需要请求体校验。
# 影响范围：/config/regions/confirm、/config/sku-groups/confirm。
class RegionRuleItem(BaseModel):
    sku_code: str
    province: str
    city: str | None = None


class RegionConfirmRequest(BaseModel):
    rules: list[RegionRuleItem]


class SkuGroupRuleItem(BaseModel):
    sku_code: str
    group_name: str
    owner_mobile: str


class SkuGroupConfirmRequest(BaseModel):
    rules: list[SkuGroupRuleItem]


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：后台管理入口需要可选登录验证，避免配置和任务触发接口暴露在无认证环境。
# 影响范围：FastAPI 后台页面、静态资源和管理 API。
AUTH_EXEMPT_PATHS = ("/health", "/login", "/logout", "/order-files/download")
ADMIN_SESSION_COOKIE = "ai_ddts_session"


def _admin_auth_response() -> JSONResponse:
    """Builds a JSON auth failure response for management-console APIs."""

    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
    )


def _is_public_path(path: str) -> bool:
    """Returns whether a path can bypass management-console authentication."""

    return path in AUTH_EXEMPT_PATHS


def _sanitize_next_path(value: str | None) -> str:
    """Keeps login redirects inside this application."""

    if not value or not value.startswith("/") or value.startswith("//"):
        return "/app"
    if value in {"/", "/app/"}:
        return "/app"
    return value


def _login_redirect(path: str) -> RedirectResponse:
    """Redirects browser requests to the login page with a safe return path."""

    query = urlencode({"next": _sanitize_next_path(path)}, safe="/")
    return RedirectResponse(url=f"/login?{query}", status_code=303)


def _should_redirect_to_login(request: Request) -> bool:
    """Returns whether an unauthenticated request is a browser page request."""

    path = request.url.path
    if request.method != "GET":
        return False
    return path in {"/", "/app", "/app/"} or path.startswith("/static")


def _session_signature(username: str, secret: str) -> str:
    """Signs a session username without exposing the configured password."""

    return hmac.HMAC(
        secret.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_session_token(username: str, secret: str) -> str:
    """Builds a compact signed session token for the admin console."""

    return f"{username}:{_session_signature(username, secret)}"


def _has_valid_session_cookie(token: str | None, username: str, secret: str) -> bool:
    """Validates the signed admin session cookie."""

    if not token:
        return False
    provided_user, separator, provided_signature = token.partition(":")
    if not separator:
        return False
    return hmac.compare_digest(provided_user, username) and hmac.compare_digest(
        provided_signature,
        _session_signature(provided_user, secret),
    )


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：本地预览环境中浏览器可能复用旧 app.js，导致规则配置 tab 不执行最新联动逻辑。
# 影响范围：/static 静态资源缓存策略。
class NoCacheStaticFiles(StaticFiles):
    """Serves static files with no-store headers for local preview reliability."""

    async def get_response(self, path: str, scope: dict[str, object]):
        """Adds cache-control headers to Starlette static file responses."""

        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


# === MODIFIED END ===


def create_app(api_service: ApiService | None = None) -> FastAPI:
    """Creates the FastAPI app and delegates work to application services."""

    load_dotenv()
    resolved_config_path = resolve_config_path()
    service = api_service or ApiService(config_path=resolved_config_path)

    # Load once at startup for the download endpoint.
    _app_config = ConfigService().load(service.config_path)
    _order_file_dir = Path(_app_config.output.order_file_dir).resolve()
    _download_secret_key_env = _app_config.download.secret_key_env

    # === MODIFIED START ===
    # 原因：使用 FastAPI lifespan 管理 Scheduler tick loop，避免 on_event 过时警告。
    # 影响范围：FastAPI 生命周期。
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Starts and stops background application services."""

        await service.start_scheduler_loop()
        try:
            yield
        finally:
            await service.stop_scheduler_loop()

    # === MODIFIED END ===

    app = FastAPI(
        title="厂直订单定时推送功能",
        version="0.1.0",
        lifespan=lifespan,
    )
    # === MODIFIED START ===
    # 原因：后台一旦配置管理员密码，所有管理入口都必须先通过登录验证。
    # 影响范围：/app、/static、配置接口、任务触发接口和查询接口。
    admin_password = os.environ.get("AI_DDTS_ADMIN_PASSWORD", "").strip()
    admin_username = os.environ.get("AI_DDTS_ADMIN_USER", "admin").strip() or "admin"
    session_secret = os.environ.get("AI_DDTS_SESSION_SECRET", "").strip() or admin_password
    if admin_password:
        @app.middleware("http")
        async def admin_session_auth(request: Request, call_next):
            """Protects management-console routes with signed browser sessions."""

            if _is_public_path(request.url.path):
                return await call_next(request)
            if _has_valid_session_cookie(
                request.cookies.get(ADMIN_SESSION_COOKIE),
                admin_username,
                session_secret,
            ):
                return await call_next(request)
            if _should_redirect_to_login(request):
                return _login_redirect(str(request.url.path))
            return _admin_auth_response()

    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：提供首版原生静态前端页面，FastAPI 仅做静态资源托管。
    # 影响范围：/app 页面和 /static 静态资源。
    static_dir = Path(__file__).parent / "static"
    # === MODIFIED START ===
    # 原因：避免浏览器沿用旧静态资源，导致规则 tab 联动修复不生效。
    # 影响范围：/static 静态资源响应头。
    app.mount("/static", NoCacheStaticFiles(directory=static_dir), name="static")
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：后台需要像常规管理系统一样使用登录页和浏览器 Cookie 保存登录状态。
    # 影响范围：/login、/logout 和 /app 访问前的会话校验。
    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        """Serves the admin login page."""

        return FileResponse(
            static_dir / "login.html",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/login", include_in_schema=False)
    async def login(request: Request) -> Response:
        """Creates a signed admin session cookie after password validation."""

        body = (await request.body()).decode("utf-8")
        fields = parse_qs(body, keep_blank_values=True)
        provided_user = fields.get("username", [""])[0]
        provided_password = fields.get("password", [""])[0]
        next_path = _sanitize_next_path(fields.get("next", [request.query_params.get("next")])[0])
        if not admin_password or (
            hmac.compare_digest(provided_user, admin_username)
            and hmac.compare_digest(provided_password, admin_password)
        ):
            response = RedirectResponse(url=next_path, status_code=303)
            response.set_cookie(
                ADMIN_SESSION_COOKIE,
                _build_session_token(admin_username, session_secret),
                httponly=True,
                samesite="lax",
                max_age=7 * 24 * 60 * 60,
            )
            return response
        return HTMLResponse(
            "<!doctype html><title>Login failed</title><p>Authentication failed</p>",
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/logout", include_in_schema=False)
    def logout() -> RedirectResponse:
        """Clears the admin session cookie and returns to the login page."""

        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(ADMIN_SESSION_COOKIE)
        return response
    # === MODIFIED END ===

    @app.get("/", include_in_schema=False)
    def frontend_root() -> RedirectResponse:
        """Redirects the service root to the management console."""

        return RedirectResponse(url="/app", status_code=303)

    @app.get("/app", include_in_schema=False)
    def frontend_app() -> FileResponse:
        """Serves the static management console."""

        # === MODIFIED START ===
        # 原因：规则配置页仍可能打开旧 HTML，显式禁用本地预览缓存。
        # 影响范围：/app HTML 响应头。
        return FileResponse(
            static_dir / "index.html",
            headers={"Cache-Control": "no-store"},
        )
        # === MODIFIED END ===

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：配置服务校验失败时，接口层只负责 HTTP 状态码转换，不写业务逻辑。
    # 影响范围：配置相关接口的错误响应。
    @app.exception_handler(ValueError)
    def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        """Maps application validation errors to HTTP 400 responses."""

        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：限发区域 Excel 导入需要结构化错误信息，方便前端展示行号、列名、原因和建议。
    # 影响范围：/config/regions/upload-xlsx 接口的错误响应。
    @app.exception_handler(ImportRuleError)
    def import_rule_error_handler(_request: Request, exc: ImportRuleError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": str(exc),
                "row": exc.row,
                "column": exc.column,
                "reason": exc.reason,
                "suggestion": exc.suggestion,
            },
        )

    # === MODIFIED END ===

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Returns service health status."""

        return {"status": "ok", "env": get_env()}

    @app.get("/order-files/download", tags=["order-files"])
    def download_order_file(filename: str, sig: str) -> FileResponse:
        """Downloads a signed order file by filename."""

        secret_key = os.environ.get(_download_secret_key_env, "")
        if not secret_key:
            raise HTTPException(status_code=503, detail="Download service not configured")

        expected_sig = hmac.HMAC(
            secret_key.encode("utf-8"),
            filename.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, sig):
            raise HTTPException(status_code=403, detail="Invalid signature")

        # === MODIFIED START ===
        # 原因：推送/上传文件统一改为 xlsx，下载入口只允许 Excel 订单文件。
        # 影响范围：/order-files/download 文件名校验。
        if not filename.endswith(".xlsx") or "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        # === MODIFIED END ===

        file_path = (_order_file_dir / filename).resolve()
        try:
            file_path.relative_to(_order_file_dir)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid filename")

        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        # === MODIFIED START ===
        # 原因：推送/上传文件统一改为 Excel，下载响应需要匹配文件类型。
        # 影响范围：/order-files/download 响应头。
        return FileResponse(path=file_path, media_type=EXCEL_MEDIA_TYPE, filename=filename)
        # === MODIFIED END ===

    @app.get("/config", tags=["config"])
    def get_config() -> dict[str, object]:
        """Returns current application configuration."""

        return service.get_config()

    # === MODIFIED START ===
    # 原因：提供配置维护入口，router 只委托应用服务处理。
    # 影响范围：FastAPI 配置管理接口。
    @app.put("/config", tags=["config"])
    def replace_config(payload: dict[str, object]) -> dict[str, object]:
        """Replaces current application configuration."""

        return service.replace_config(payload)

    @app.put("/config/rules", tags=["config"])
    def update_rule_config(payload: dict[str, object]) -> dict[str, object]:
        """Updates rule configuration fields."""

        return service.update_rule_config(payload)

    # === MODIFIED START ===
    # 原因：前端 RPA 开关需要只修改 rpa.enabled 字段。
    # 影响范围：RPA 配置更新接口。
    @app.put("/config/rpa", tags=["config"])
    def update_rpa_config(payload: dict[str, object]) -> dict[str, object]:
        """Updates only the rpa.enabled field."""

        return service.update_rpa_config(payload)

    # === MODIFIED END ===

    @app.post("/config/regions/upload-xlsx", tags=["config"])
    async def upload_region_xlsx(file: UploadFile = File(...)) -> dict[str, object]:
        """Uploads an xlsx file, parses restricted regions, returns diff preview."""

        content = await file.read()
        return service.preview_region_xlsx(content, file.filename or "upload.xlsx")

    @app.post("/config/regions/confirm", tags=["config"])
    def confirm_region_import(body: RegionConfirmRequest) -> dict[str, object]:
        """Writes confirmed region rules to config."""

        return service.confirm_region_import([r.model_dump() for r in body.rules])

    @app.post("/config/sku-groups/upload-xlsx", tags=["config"])
    async def upload_sku_group_xlsx(file: UploadFile = File(...)) -> dict[str, object]:
        """Uploads an xlsx file, parses SKU groups, returns diff preview."""

        content = await file.read()
        return service.preview_sku_group_xlsx(content, file.filename or "upload.xlsx")

    @app.post("/config/sku-groups/confirm", tags=["config"])
    def confirm_sku_group_import(body: SkuGroupConfirmRequest) -> dict[str, object]:
        """Writes confirmed SKU group rules to config."""

        return service.confirm_sku_group_import([r.model_dump() for r in body.rules])

    # === MODIFIED START ===
    # 原因：规则配置页需要手动触发 SKU 群推送人配置同步，router 只负责委托应用服务。
    # 影响范围：规则配置页同步按钮。
    @app.post("/config/sku-groups/sync-caller-configs", tags=["config"])
    def sync_sku_group_caller_configs() -> dict[str, object]:
        """Synchronizes SKU group caller configs to push-center."""

        return service.sync_sku_group_caller_configs()
    # === MODIFIED END ===

    @app.post("/config/excluded-skus/upload-xlsx", tags=["config"])
    async def upload_excluded_sku_xlsx(file: UploadFile = File(...)) -> dict[str, object]:
        """Uploads an xlsx file, parses SKUs, and merges into excluded_skus."""

        content = await file.read()
        return service.upload_excluded_sku_xlsx(content, file.filename or "upload.xlsx")

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：提供 ERP SKU-供应商对照数据的临时批量接收与查询入口。
    # 影响范围：FastAPI 供应商映射接口。
    @app.get("/supplier-mappings", tags=["supplier-mappings"])
    def get_supplier_mappings() -> dict[str, object]:
        """Returns SKU to supplier mappings."""

        return service.get_supplier_mappings()

    @app.put("/supplier-mappings", tags=["supplier-mappings"])
    def replace_supplier_mappings(payload: dict[str, object]) -> dict[str, object]:
        """Replaces SKU to supplier mappings."""

        return service.replace_supplier_mappings(payload)

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：提供异常订单查询和 CSV 下载入口，router 只做 HTTP 响应适配。
    # 影响范围：FastAPI 异常订单接口。
    @app.get("/exception-orders", tags=["exception-orders"])
    def list_exception_orders(limit: int = 100) -> dict[str, object]:
        """Returns recent exception order details."""

        return service.list_exception_orders(limit)

    @app.get("/exception-orders/download", tags=["exception-orders"])
    def download_exception_orders(trace_id: str | None = None) -> FileResponse:
        """Downloads exception order details as CSV."""

        # === MODIFIED START ===
        # 原因：任务清单需要按批次下载异常订单，router 只透传查询参数给应用层。
        # 影响范围：异常订单下载接口。
        file_path = service.export_exception_orders(trace_id=trace_id)
        # === MODIFIED END ===
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=file_path.name,
        )

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：任务清单需要按批次下载正常推送订单明细。
    # 影响范围：FastAPI 任务下载接口。
    @app.get("/tasks/{trace_id}/pushed-orders/download", tags=["tasks"])
    def download_pushed_orders(trace_id: str) -> FileResponse:
        """Downloads normal pushed order details for one task."""

        file_path = service.export_pushed_orders(trace_id)
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=file_path.name,
        )

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：前端需要查询和下载面向业务人员的执行日志，router 仅透传筛选参数给应用层。
    # 影响范围：执行日志接口。
    @app.get("/execution-logs", tags=["execution-logs"])
    def list_execution_logs(
        limit: int | None = None,
        trace_id: str | None = None,
        stage: str | None = None,
        result: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> dict[str, object]:
        """Returns visual execution logs."""

        return service.list_execution_logs(
            limit=limit,
            trace_id=trace_id,
            stage=stage,
            result=result,
            start_at=start_at,
            end_at=end_at,
        )

    @app.get("/execution-logs/download", tags=["execution-logs"])
    def download_execution_logs(
        trace_id: str | None = None,
        stage: str | None = None,
        result: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> FileResponse:
        """Downloads visual execution logs as CSV."""

        file_path = service.export_execution_logs(
            trace_id=trace_id,
            stage=stage,
            result=result,
            start_at=start_at,
            end_at=end_at,
        )
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=file_path.name,
        )

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：提供固定时间 Scheduler 的状态查询和 tick 触发入口，router 只委托应用服务。
    # 影响范围：FastAPI 调度器接口。
    @app.get("/scheduler/status", tags=["scheduler"])
    def get_scheduler_status() -> dict[str, object]:
        """Returns fixed-time scheduler status."""

        return service.get_scheduler_status()

    @app.post("/scheduler/tick", tags=["scheduler"])
    def tick_scheduler() -> dict[str, object]:
        """Evaluates the fixed-time scheduler once."""

        return service.tick_scheduler()

    @app.get("/scheduler/loop/status", tags=["scheduler"])
    def get_scheduler_loop_status() -> dict[str, object]:
        """Returns background scheduler loop status."""

        return service.get_scheduler_loop_status()

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：定时任务失败后需要强行修改上次运行时间，允许重新触发。
    # 影响范围：Scheduler 状态修改接口。
    @app.put("/scheduler/state", tags=["scheduler"])
    def update_scheduler_state(
        schedule_id: str = "default",
        last_run_date: str | None = None,
        last_run_at: str | None = None,
        last_trace_id: str | None = None,
    ) -> dict[str, object]:
        """Force-updates the persisted scheduler state."""

        return service.update_scheduler_state(
            schedule_id,
            last_run_date=last_run_date,
            last_run_at=last_run_at,
            last_trace_id=last_trace_id,
        )

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：任务来源已配置化，提供不带 mock 语义的正式运行入口。
    # 影响范围：FastAPI 任务运行接口。
    @app.post("/tasks/run", tags=["tasks"])
    def run_task() -> dict[str, object]:
        """Runs one configured task."""

        return service.run_task()

    @app.post("/tasks/mock-run", tags=["tasks"])
    def run_mock_task() -> dict[str, object]:
        """Runs one configured task through a backward-compatible endpoint."""

        return service.run_mock_task()

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：定时任务失败后需要按原时间窗口重新执行。
    # 影响范围：FastAPI 任务重推接口。
    @app.post("/tasks/{trace_id}/repush", tags=["tasks"])
    def repush_task(trace_id: str) -> dict[str, object]:
        """Re-runs a task using the same time window as a previous run."""

        return service.repush_task(trace_id)

    # === MODIFIED END ===

    @app.get("/tasks/latest", tags=["tasks"])
    def get_latest_task() -> dict[str, object]:
        """Returns latest configured task summary."""

        summary = service.get_latest_summary()
        if summary is None:
            raise HTTPException(status_code=404, detail="No task has been run yet")
        return summary

    # === MODIFIED START ===
    # 原因：提供任务运行历史查询入口，router 只委托应用服务。
    # 影响范围：FastAPI 任务查询接口。
    @app.get("/tasks/history", tags=["tasks"])
    def list_task_history(limit: int = 20) -> list[dict[str, object]]:
        """Returns recent local task run summaries."""

        return service.list_recent_summaries(limit)

    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：临时推送需要独立的运行、列表和下载接口。
    # 影响范围：FastAPI 临时推送接口。
    @app.post("/temp-push/run", tags=["temp-push"])
    def run_temp_push(body: dict[str, object]) -> dict[str, object]:
        """Runs one temporary push with a 2-rule engine."""

        from application.temp_push_runner import run_temp_push as _run
        window_start_str = body.get("window_start")
        # === MODIFIED START ===
        # 原因：结束时间改为从定时任务 run_at 计算，不再依赖任务运行历史 trace_id。
        # 影响范围：临时推送执行接口。
        window_end_run_at = body.get("window_end_run_at")
        if not window_start_str or not window_end_run_at:
            raise HTTPException(status_code=400, detail="window_start 和 window_end_run_at 必填")
        window_start = datetime.fromisoformat(str(window_start_str))
        return _run(window_start=window_start, window_end_run_at=str(window_end_run_at))
        # === MODIFIED END ===

    @app.get("/temp-push/orders", tags=["temp-push"])
    def list_temp_push_orders() -> dict[str, object]:
        """Lists all temporary push records grouped by temp_push_id."""

        from application.special_push_order_store import SpecialPushOrderStore
        base_dir = Path("outputs") / "special_push"
        if not base_dir.exists():
            return {"items": []}
        items = []
        for child in sorted(base_dir.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            store = SpecialPushOrderStore(temp_push_id=child.name)
            orders = store.list_all()

            # === MODIFIED START ===
            # 原因：修复日志 details 键名与 temp_push_runner 实际写入不匹配的问题，
            #       同时补充 delivery_count 读取。
            # 影响范围：临时推送历史列表数据展示。
            # === MODIFIED END ===
            push_status = ""
            passed_count = 0
            ignored_count = 0
            error_count = 0
            delivery_count = 0
            # === MODIFIED START ===
            # 原因：临时推送历史页参考任务清单，需要展示批次创建时间。
            # 影响范围：/temp-push/orders 返回字段。
            created_at = ""
            # === MODIFIED END ===
            window_start = ""
            window_end = ""
            failure_reason = ""
            # === MODIFIED START ===
            # 原因：临时推送历史行需要返回日志中的 trace_id，避免接口因未定义变量失败。
            # 影响范围：/temp-push/orders 返回字段与前端历史列表。
            trace_id = ""
            # === MODIFIED END ===
            log_path = child / "execution_logs.json"
            if log_path.exists():
                try:
                    import json as _json
                    logs = _json.loads(log_path.read_text(encoding="utf-8"))
                    for log in logs:
                        details = log.get("details", {})
                        # === MODIFIED START ===
                        # 原因：从批次日志提取 trace_id 和 details 时需要容错，保证历史列表能展示已有产物。
                        # 影响范围：临时推送历史统计与下载按钮状态。
                        if not isinstance(details, dict):
                            details = {}
                        if not trace_id:
                            trace_id = str(log.get("trace_id", "") or "")
                        # === MODIFIED END ===
                        if not created_at:
                            created_at = log.get("created_at", "")
                        # === MODIFIED START ===
                        # 原因：日志 stage/result 存的是中文枚举值（.value），需用中文匹配。
                        # 影响范围：临时推送历史列表数据展示。
                        # === MODIFIED END ===
                        if log.get("stage") == "临时推送" and not window_start:
                            window_start = details.get("window_start", "")
                            window_end = details.get("window_end", "")
                        if log.get("stage") == "规则判断":
                            passed_count = details.get("passed", 0)
                            ignored_count = details.get("ignored", 0)
                            error_count = details.get("error", 0)
                        if log.get("stage") == "推送群":
                            # === MODIFIED START ===
                            # 原因：历史列表状态应展示结构化推送状态值（如“已推送”），不是日志摘要。
                            # 影响范围：临时推送历史列表状态徽标。
                            push_status = details.get("push_status", "") or log.get("summary", "")
                            # === MODIFIED END ===
                            delivery_count = details.get("delivery_count", 0)
                        if log.get("result") == "失败":
                            failure_reason = log.get("summary", "")
                except Exception:
                    pass

            if not push_status:
                if orders:
                    push_status = "已推送"
                else:
                    push_status = "无订单"

            items.append({
                "temp_push_id": child.name,
                "trace_id": trace_id,
                "created_at": created_at,
                "order_count": len(orders),
                "push_status": push_status,
                "passed_count": passed_count,
                "ignored_count": ignored_count,
                "error_count": error_count,
                "delivery_count": delivery_count,
                "window_start": window_start,
                "window_end": window_end,
                "failure_reason": failure_reason,
            })
        return {"items": items}

    # === MODIFIED START ===
    # 原因：trace_id 改为可选，不传时下载该批次全部正常推送订单。
    # 影响范围：临时推送正常推送订单下载接口。
    # === MODIFIED END ===
    @app.get("/temp-push/{temp_push_id}/orders/download", tags=["temp-push"])
    def download_temp_push_orders(temp_push_id: str, trace_id: str | None = None) -> FileResponse:
        """Downloads temporary push order details as CSV."""

        from application.special_push_order_store import SpecialPushOrderStore
        store = SpecialPushOrderStore(temp_push_id=temp_push_id)
        file_path = store.export_csv(trace_id)
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=file_path.name,
        )

    # === MODIFIED START ===
    # 原因：临时推送需要下载异常订单 CSV，与定时任务清单的异常订单下载对齐。
    # 影响范围：临时推送异常订单下载接口。
    @app.get("/temp-push/{temp_push_id}/exception-orders/download", tags=["temp-push"])
    def download_temp_push_exception_orders(temp_push_id: str) -> FileResponse:
        """Downloads temporary push exception orders as CSV."""

        from application.exception_order_store import ExceptionOrderStore
        base_dir = Path("outputs") / "special_push" / temp_push_id
        history_path = base_dir / "exception_orders.json"
        if not history_path.exists():
            raise HTTPException(status_code=404, detail="未找到异常订单记录")
        store = ExceptionOrderStore(
            history_path=history_path,
            export_dir=base_dir / "exception_order_exports",
        )
        file_path = store.export_csv()
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=file_path.name,
        )

    # === MODIFIED START ===
    # 原因：临时推送需要下载执行日志 CSV，与定时任务的执行日志下载对齐。
    # 影响范围：临时推送执行日志下载接口。
    @app.get("/temp-push/{temp_push_id}/execution-logs/download", tags=["temp-push"])
    def download_temp_push_execution_logs(temp_push_id: str) -> FileResponse:
        """Downloads temporary push execution logs as CSV."""

        from application.execution_log_store import ExecutionLogStore
        base_dir = Path("outputs") / "special_push" / temp_push_id
        log_path = base_dir / "execution_logs.json"
        if not log_path.exists():
            raise HTTPException(status_code=404, detail="未找到执行日志记录")
        store = ExecutionLogStore(
            history_path=log_path,
            export_dir=base_dir / "execution_log_exports",
        )
        file_path = store.export_csv()
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=file_path.name,
        )
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：支持任务付款状态查询和付款回执上传，router 只做上传文件适配。
    # 影响范围：FastAPI 付款追踪接口。
    @app.get("/tasks/{trace_id}/payment", tags=["tasks"])
    def get_task_payment(trace_id: str) -> dict[str, object]:
        """Returns payment status for one task."""

        return service.get_payment_status(trace_id)

    @app.post("/tasks/{trace_id}/payment-receipt", tags=["tasks"])
    async def upload_task_payment_receipt(
        trace_id: str,
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        """Uploads payment receipt for one task."""

        content = await file.read()
        return service.upload_payment_receipt(
            trace_id=trace_id,
            original_filename=file.filename or "receipt",
            content=content,
        )

    # === MODIFIED END ===

    return app


app = create_app()
