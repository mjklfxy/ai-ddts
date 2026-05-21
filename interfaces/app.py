from __future__ import annotations

import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

# === MODIFIED START ===
# 原因：配置接口需要把应用层校验错误转换为 HTTP 400 响应。
# 影响范围：接口层错误响应映射。
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
# === MODIFIED END ===

from application.api_service import ApiService
from application.config_service import ConfigService


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

    service = api_service or ApiService()

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
    # 原因：提供首版原生静态前端页面，FastAPI 仅做静态资源托管。
    # 影响范围：/app 页面和 /static 静态资源。
    static_dir = Path(__file__).parent / "static"
    # === MODIFIED START ===
    # 原因：避免浏览器沿用旧静态资源，导致规则 tab 联动修复不生效。
    # 影响范围：/static 静态资源响应头。
    app.mount("/static", NoCacheStaticFiles(directory=static_dir), name="static")
    # === MODIFIED END ===

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

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Returns service health status."""

        return {"status": "ok"}

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

        if not filename.endswith(".csv") or "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_path = (_order_file_dir / filename).resolve()
        try:
            file_path.relative_to(_order_file_dir)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid filename")

        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(path=file_path, media_type="text/csv", filename=filename)

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

    @app.post("/config/regions/upload-xlsx", tags=["config"])
    async def upload_region_xlsx(file: UploadFile = File(...)) -> dict[str, object]:
        """Uploads an xlsx file, parses restricted regions, and merges into config."""

        content = await file.read()
        return service.upload_region_xlsx(content, file.filename or "upload.xlsx")

    @app.post("/config/sku-groups/upload-xlsx", tags=["config"])
    async def upload_sku_group_xlsx(file: UploadFile = File(...)) -> dict[str, object]:
        """Uploads an xlsx file, parses SKU groups, and merges into config."""

        content = await file.read()
        return service.upload_sku_group_xlsx(content, file.filename or "upload.xlsx")

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
