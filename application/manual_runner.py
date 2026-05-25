from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from application.config_service import AppConfig, ConfigService

# === MODIFIED START ===
# 原因：任务执行过程需要生成面向业务人员的可视化执行日志。
# 影响范围：run_once 关键阶段日志持久化。
from application.execution_log_store import ExecutionLogRecord, ExecutionLogStore

# === MODIFIED END ===
# === MODIFIED START ===
# 原因：任务运行需要将规则失败的异常订单明细持久化，供接口查询和下载。
# 影响范围：手动任务运行和本地 API mock-run。
from application.exception_order_store import ExceptionOrderStore

# === MODIFIED END ===
# === MODIFIED START ===
# 原因：推送/上传订单文件统一改为 Excel。
# 影响范围：Pipeline 构建和异常订单文件生成。
from application.file_generator import ExcelFileGenerator
# === MODIFIED END ===
from application.order_splitter import OrderSplitter
from application.pipeline import Pipeline, PipelineRunResult

# === MODIFIED START ===
# 原因：任务运行需要持久化正常推送订单明细，供任务清单按批次下载。
# 影响范围：手动任务运行和本地 API mock-run。
from application.pushed_order_store import PushedOrderStore

# === MODIFIED END ===
# === MODIFIED START ===
# 原因：推送订单和异常订单的供应商查询改用云仓 API 实时查询，支持自动刷新。
# 影响范围：run_once 与导出供应商查询。
from infrastructure.cloud_warehouse_client import CloudWarehouseClient
# === MODIFIED END ===

# === MODIFIED END ===
# === MODIFIED START ===
# 原因：任务批次编码需要在任务运行入口按历史批次做日内累计。
# 影响范围：run_once 任务上下文创建。
from application.task_code import DailyTaskCodeGenerator

# === MODIFIED END ===
from application.task_service import TaskService
from domain.enums.execution_log import ExecutionLogResult, ExecutionLogStage
from domain.rule_engine import RuleEngine
from domain.enums.status import KingdeeStatus, PushStatus
from domain.exception_order import ExceptionOrder
from domain.rules.customer_type_rule import CustomerTypeRule
from domain.rules.group_rule import GroupRule
from domain.rules.order_prefix_rule import OrderPrefixRule
from domain.rules.region_rule import RegionRule
from domain.rules.sku_rule import SkuServiceRule
from domain.rules.warehouse_rule import WarehouseRule

from infrastructure.jikeyun_client import (
    JikeyunClient,
    JikeyunCredentials,
    # === MODIFIED START ===
    # 原因：配置切换到真实吉客云来源时需要 HTTP transport。
    # 影响范围：任务运行订单来源。
    JikeyunHttpTransport,
    # === MODIFIED END ===
    JikeyunPageResult,
    Transport,
)
from infrastructure.kingdee_service import (
    KingdeeHttpTransport,
    KingdeeService,
    KingdeeSubmitResult,
    KingdeeTransport,
)
from infrastructure.message_adapter import MessageAdapter
from infrastructure.qixin_client import (
    QixinClient,
    QixinSender,
    RemoteUserResolver,
    RemoteUserResolverError,
    make_link_content_builder,
    make_upload_content_builder,
)
# === MODIFIED START ===
# 原因：文件生成后自动上传到公网文件服务器供群消息使用。
# 影响范围：手动运行、API 运行和 Scheduler 运行。
from infrastructure.file_upload_client import FileUploadClient
# === MODIFIED END ===
from shared.logging.logger import log_error, log_info


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Summary returned by one manual task run."""

    trace_id: str
    passed_count: int
    ignored_count: int
    error_count: int
    delivery_count: int
    kingdee_tracking_id: str | None
    # === MODIFIED START ===
    # 原因：任务历史需要持久化状态、时间窗和失败信息，供接口和前端追踪。
    # 影响范围：RunSummary、TaskRunStore 和任务 API 响应。
    task_name: str | None = None
    created_at: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    push_status: PushStatus = PushStatus.PENDING
    kingdee_status: KingdeeStatus = KingdeeStatus.PENDING
    failure_stage: str | None = None
    failure_reason: str | None = None
    # === MODIFIED END ===


# === MODIFIED START ===
# 原因：任务运行需要读取 ERP 同步的 SKU-供应商对照数据。
# 影响范围：手动运行入口和 API mock-run。
def run_once(
    config_path: str | Path = Path("config") / "config.json",
    supplier_mapping_path: str | Path = Path("outputs") / "sku_supplier_mappings.json",
    exception_order_path: str | Path = Path("outputs") / "exception_orders.json",
    # === MODIFIED START ===
    # 原因：每次任务需要持久化正常推送订单明细，供任务清单按批次下载。
    # 影响范围：run_once 任务运行输出。
    pushed_order_path: str | Path = Path("outputs") / "pushed_orders.json",
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：任务运行需要持久化可视化执行日志，供页面查询和下载。
    # 影响范围：run_once 任务执行输出。
    execution_log_path: str | Path = Path("outputs") / "execution_logs.json",
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：API/定时任务需要基于持久化历史生成 yyyyMMdd + 四位数累计批次编码。
    # 影响范围：手动任务、API 任务和 Scheduler 任务上下文创建。
    existing_task_codes_provider: Callable[[], Iterable[str]] | None = None,
    trace_id_generator: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
    scheduled_run_at: str | None = None,
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：多定时任务需要以上次任务的 run_at 作为本次窗口起点，避免重复拉单。
    # 影响范围：Scheduler 触发的 run_once 窗口计算。
    scheduled_last_run_at: str | None = None,
    # === MODIFIED END ===
) -> RunSummary:
    """Runs one configured task with configured rules."""

    config = ConfigService().load(config_path)
    supplier_client = CloudWarehouseClient(local_path=supplier_mapping_path)
    # === MODIFIED START ===
    # 原因：批次号日期、任务创建时间和拉单窗口结束时间需要使用同一个 now。
    # 影响范围：run_once 生成的 TaskContext。
    now_provider = clock or datetime.now
    now = now_provider()
    task_clock = lambda: now
    task_trace_id_generator = trace_id_generator
    if task_trace_id_generator is None and existing_task_codes_provider is not None:
        task_trace_id_generator = DailyTaskCodeGenerator(
            existing_codes_provider=existing_task_codes_provider,
            clock=task_clock,
        )
    window_start = now - timedelta(minutes=config.task.window_minutes)
    window_end = now
    if scheduled_run_at is not None:
        window_end = _scheduled_window_end(now, scheduled_run_at)
        if scheduled_last_run_at is not None:
            window_start = datetime.fromisoformat(scheduled_last_run_at)
        else:
            window_start = window_end - timedelta(days=1)
    task_context = TaskService(
        trace_id_generator=task_trace_id_generator,
        clock=task_clock,
    ).create_task(
        task_name=config.task.name,
        window_start=window_start,
        window_end=window_end,
    )
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：可视化日志以任务批次 trace_id 为主线，必须在任务上下文创建后开始记录。
    # 影响范围：run_once 执行日志。
    execution_log_store = ExecutionLogStore(history_path=execution_log_path)
    _append_execution_log(
        execution_log_store,
        task_context,
        ExecutionLogStage.TASK,
        ExecutionLogResult.SUCCESS,
        "任务开始执行",
        impact=f"订单时间窗口：{task_context.window_start.isoformat()} 至 {task_context.window_end.isoformat()}",
    )
    # === MODIFIED END ===
    pipeline = build_pipeline_from_config(
        config, supplier_mapping_path=supplier_mapping_path
    )
    try:
        # === MODIFIED START ===
        # 原因：任务订单来源需要支持 mock 与真实吉客云配置切换。
        # 影响范围：手动运行、API 运行和 Scheduler 运行。
        try:
            orders = fetch_orders_from_config(config=config, task_context=task_context)
        except Exception as exc:
            _append_execution_log(
                execution_log_store,
                task_context,
                ExecutionLogStage.FETCH,
                ExecutionLogResult.FAILED,
                "订单抓取失败",
                impact="本次任务没有拿到订单数据。",
                suggestion="检查订单来源配置、吉客云凭据、网络连通性和任务时间窗口。",
                details={
                    "error_type": exc.__class__.__name__,
                    "reason": _safe_exception_reason(exc),
                },
            )
            raise
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：抓单结果需要进入可视化执行日志，帮助无开发背景人员判断本次是否拿到订单。
        # 影响范围：run_once 抓单阶段日志。
        _append_execution_log(
            execution_log_store,
            task_context,
            ExecutionLogStage.FETCH,
            ExecutionLogResult.SUCCESS,
            "已完成订单抓取",
            impact=f"本次抓取订单 {len(orders)} 单",
            suggestion="如数量不符合预期，优先检查任务时间窗口和订单来源配置。",
            details={"order_count": len(orders)},
        )
        # === MODIFIED END ===
        result = pipeline.run(
            task_context=task_context,
            orders=orders,
        )
        # === MODIFIED START ===
        # 原因：pipeline 已生成异常订单明细，这里负责在应用层持久化。
        # 影响范围：异常订单查询和下载接口数据来源。
        # === MODIFIED START ===
        # 原因：补全异常订单的推送群信息和供应商名称后再落盘。
        # 影响范围：exception_orders.json 字段完整性。
        enriched_exception_orders = _enrich_exception_orders(
            result.exception_orders,
            sku_group_map=config.rules.sku_group_map,
            supplier_client=supplier_client,
        )
        # === MODIFIED START ===
        # 原因：异常订单需要按厂家生成 error Excel 文件，供业务人员按群查看和处理。
        # 影响范围：/outputs/order_files/error/ 目录下的异常订单文件。
        _generate_error_files(
            enriched_exception_orders,
            output_dir=config.output.order_file_dir,
            clock=task_clock,
        )
        # === MODIFIED END ===
        ExceptionOrderStore(history_path=exception_order_path).append_many(
            task_context=task_context,
            exception_orders=enriched_exception_orders,
        )
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：pipeline 已产出正常推送批次，这里负责在应用层持久化可下载的订单明细。
        # 影响范围：正常推送订单明细下载数据来源。
        PushedOrderStore(history_path=pushed_order_path).append_many(
            task_context=task_context,
            deliveries=result.deliveries,
            supplier_client=supplier_client,
        )
        # === MODIFIED END ===
    except Exception as exc:
        # === MODIFIED START ===
        # 原因：任务中断需要在可视化日志中留下业务可读失败原因。
        # 影响范围：run_once 异常路径日志。
        _append_execution_log(
            execution_log_store,
            task_context,
            ExecutionLogStage.TASK,
            ExecutionLogResult.FAILED,
            "任务执行中断",
            impact="本次任务没有形成完整结果。",
            suggestion="查看同一任务批次下失败阶段日志；如为抓单失败，检查接口凭据、网络和时间窗口。",
            details={
                "error_type": exc.__class__.__name__,
                "reason": _safe_exception_reason(exc),
            },
        )
        # === MODIFIED END ===
        raise

    # === MODIFIED START ===
    # 原因：任务完成后统一写入业务可读阶段日志，支撑前端执行日志页面。
    # 影响范围：run_once 成功路径日志。
    _append_result_execution_logs(execution_log_store, result)
    summary = summarize_result(result)
    _append_execution_log(
        execution_log_store,
        task_context,
        ExecutionLogStage.TASK,
        _task_execution_result(summary),
        "任务执行完成",
        impact=(
            f"通过 {summary.passed_count} 单，异常 {summary.error_count} 单，"
            f"忽略 {summary.ignored_count} 单，生成推送批次 {summary.delivery_count} 个"
        ),
        suggestion=_task_completion_suggestion(summary),
        details={
            "passed_count": summary.passed_count,
            "ignored_count": summary.ignored_count,
            "error_count": summary.error_count,
            "delivery_count": summary.delivery_count,
            "push_status": summary.push_status.value,
            "kingdee_status": summary.kingdee_status.value,
        },
    )
    return summary
    # === MODIFIED END ===


# === MODIFIED END ===


def build_pipeline_from_config(
    config: AppConfig,
    # === MODIFIED START ===
    # 原因：金蝶提交通道需要支持测试注入和按配置构建。
    # 影响范围：Pipeline 构建。
    env: Mapping[str, str] | None = None,
    kingdee_transport: KingdeeTransport | None = None,
    # === MODIFIED END ===
    supplier_mapping_path: str | Path = Path("outputs") / "sku_supplier_mappings.json",
) -> Pipeline:
    """Builds the local pipeline from application configuration."""
    rule_engine = RuleEngine(
        rules=[
            # === MODIFIED START ===
            # 原因：个人顾客订单（-MULTI 后缀）需要最先拦截，避免被后续规则误判为其他异常类型。
            # 影响范围：任务运行规则引擎构建。
            CustomerTypeRule(
                personal_order_suffix=config.rules.personal_order_suffix,
                enabled=config.rules.personal_order_filter_enabled,
            ),
            # === MODIFIED END ===
            OrderPrefixRule(
                allowed_prefixes=config.rules.allowed_order_prefixes,
                enabled=config.rules.order_prefix_filter_enabled,
            ),
            # === MODIFIED START ===
            # 原因：排除库房模块新增总开关，规则引擎只负责接收配置后的纯规则。
            # 影响范围：任务运行规则引擎构建。
            WarehouseRule(
                excluded_warehouses=set(config.rules.excluded_warehouses),
                enabled=config.rules.excluded_warehouses_enabled,
            ),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：SKU 规则实际是排除黑名单，不是启用白名单。
            # 影响范围：任务运行规则引擎构建。
            SkuServiceRule(
                excluded_skus=set(config.rules.excluded_skus),
                enabled=config.rules.excluded_skus_enabled,
            ),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：限发区域与 SKU 群配置新增模块级启用开关。
            # 影响范围：任务运行规则引擎构建。
            RegionRule(
                restricted_regions=config.rules.restricted_regions,
                enabled=config.rules.restricted_regions_enabled,
            ),
            GroupRule(
                sku_group_map=config.rules.sku_group_map,
                enabled=config.rules.sku_group_map_enabled,
            ),
            # === MODIFIED END ===
        ],
        log_info=log_info,
    )
    # === MODIFIED END ===
    return Pipeline(
        rule_engine=rule_engine,
        order_splitter=OrderSplitter(sku_group_map=config.rules.sku_group_map),
        file_generator=ExcelFileGenerator(output_dir=config.output.order_file_dir),
        message_sender=build_message_sender_from_config(config, env=env),
        kingdee_service=KingdeeService(
            transport=kingdee_transport
            or build_kingdee_transport_from_config(config, env=env),
            supplier_mapping_path=supplier_mapping_path,
        ),
        kingdee_enabled=config.kingdee.enabled,
        # === MODIFIED START ===
        # 原因：祺信文件直推模式需要为每个文件动态构造签名下载地址。
        # 影响范围：Pipeline._deliver_batches、MessagePayload.file_url。
        download_base_url=config.download.base_url or None,
        download_secret_key=(env or os.environ).get(config.download.secret_key_env),
        # === MODIFIED START ===
        # 原因：文件生成后自动上传到公网文件服务器。
        # 影响范围：Pipeline 推送阶段。
        upload_file=_build_upload_fn(config, env=env),
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：user_id 改为推送时惰性解析，避免 build_pipeline 阶段串行调用 270+ 次 userid API 导致卡死。
        # 影响范围：Pipeline._deliver_batches 推送阶段。
        user_resolver=_build_cached_user_resolver(config),
        # === MODIFIED END ===
        log_info=log_info,
        log_error=log_error,
    )


# === MODIFIED START ===
# 原因：金蝶采购申请需要按配置在 mock 和 HTTP 接口之间切换。
# 影响范围：任务运行金蝶提交阶段。
def build_kingdee_transport_from_config(
    config: AppConfig,
    env: Mapping[str, str] | None = None,
) -> KingdeeTransport:
    """Builds the configured Kingdee purchase request transport."""

    if config.kingdee.mode == "mock":
        return lambda request: KingdeeSubmitResult(
            tracking_id=f"LOCAL-KINGDEE-{request.trace_id}"
        )
    if config.kingdee.mode == "http":
        source_env = env or os.environ
        token = source_env.get(config.kingdee.token_env)
        return KingdeeHttpTransport(
            api_url=config.kingdee.api_url,
            token=token,
            timeout_seconds=config.kingdee.timeout_seconds,
            tracking_id_fields=config.kingdee.tracking_id_fields,
            extra_headers=config.kingdee.extra_headers,
        )
    raise ValueError(f"Unsupported Kingdee mode: {config.kingdee.mode}")


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：消息发送通道需要按配置在 mock 和祺信真实 API 之间切换。
# 影响范围：Pipeline 消息推送阶段。
def build_message_sender_from_config(
    config: AppConfig,
    env: Mapping[str, str] | None = None,
) -> MessageAdapter:
    """Builds the configured message sender from application configuration."""

    if config.qixin.mode == "mock":

        def sender(payload):
            return f"LOCAL-MSG-{payload.group_name}"
    elif config.qixin.mode == "qixin":
        source_env = env or os.environ
        secret_key = source_env.get(config.qixin.secret_key_env) or config.qixin.secret_key_env
        client = QixinClient(
            api_base_url=config.qixin.api_base_url,
            caller_id=config.qixin.caller_id,
            secret_key=secret_key,
            timeout_seconds=config.qixin.timeout_seconds,
        )
        # === MODIFIED START ===
        # 原因：文件上传到公网服务器后，内容构建器应使用已上传的 file_url。
        # 影响范围：群消息内容生成。
        if config.upload.enabled and config.upload.api_url:
            sender = QixinSender(
                client=client,
                content_builder=make_upload_content_builder(),
                push_mode=config.qixin.push_mode,
            )
        elif source_env.get(config.download.secret_key_env, "") and config.download.base_url:
            content_builder = make_link_content_builder(
                config.download.base_url,
                source_env.get(config.download.secret_key_env, ""),
            )
            sender = QixinSender(
                client=client,
                content_builder=content_builder,
                push_mode=config.qixin.push_mode,
            )
        else:
            sender = QixinSender(
                client=client,
                push_mode=config.qixin.push_mode,
            )
        # === MODIFIED END ===
    else:
        raise ValueError(f"Unsupported message sender mode: {config.qixin.mode}")

    return MessageAdapter(
        sender=sender,
        max_attempts=config.message.max_attempts,
        retry_interval_seconds=config.message.retry_interval_seconds,
        log_info=log_info,
        log_error=log_error,
    )


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：user_id 改为推送时惰性解析，避免 build_pipeline 阶段串行调用 270+ 次 userid API 导致卡死。
# 影响范围：Pipeline._deliver_batches 推送阶段。
def _build_cached_user_resolver(config: AppConfig):
    """Builds a cached user_id resolver, or None when not in qixin mode.

    Each unique mobile is resolved at most once per run; results are cached
    in memory. Resolution happens lazily when the pipeline pushes a batch.
    """
    if config.qixin.mode != "qixin":
        return None

    resolver = RemoteUserResolver(
        api_url=config.qixin.userid_api_url,
        timeout_seconds=config.qixin.timeout_seconds,
    )
    cache: dict[str, str] = {}

    def resolve(owner_mobile: str) -> str:
        if not owner_mobile or not owner_mobile.strip():
            return ""
        mobile = owner_mobile.strip()
        if mobile in cache:
            return cache[mobile]
        try:
            user_id = resolver.get_userid_by_mobile(mobile)
        except RemoteUserResolverError:
            user_id = mobile
        cache[mobile] = user_id
        return user_id

    return resolve


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：订单来源需要按配置在 mock 和真实吉客云之间切换，application 层只负责选择来源。
# 影响范围：run_once、API 任务运行和 Scheduler。
def fetch_orders_from_config(
    config: AppConfig,
    task_context,
    env: Mapping[str, str] | None = None,
    jikeyun_transport: Transport | None = None,
) -> tuple:
    """Fetches orders from the configured source for one task window."""

    client = build_order_source_client(
        config=config,
        env=env,
        jikeyun_transport=jikeyun_transport,
    )
    return client.fetch_orders(
        trace_id=task_context.trace_id,
        start_time=task_context.window_start,
        end_time=task_context.window_end,
    )


# === MODIFIED START ===
# 原因：定时任务需要按当前 schedule 的固定时间生成昨天到今天的 24 小时拉单窗口。
# 影响范围：Scheduler 触发的任务上下文、API 拉单窗口、RPA 时间筛选窗口。
def _scheduled_window_end(now: datetime, run_at: str) -> datetime:
    """Returns today's scheduled end time for one fixed daily schedule."""

    scheduled_time = datetime.strptime(run_at, "%H:%M").time()
    return datetime.combine(now.date(), scheduled_time)


# === MODIFIED END ===


def build_order_source_client(
    config: AppConfig,
    env: Mapping[str, str] | None = None,
    jikeyun_transport: Transport | None = None,
) -> JikeyunClient:
    """Builds the configured order source client."""

    if config.source.mode == "mock":
        return build_mock_jikeyun_client(config)
    if config.source.mode == "jikeyun":
        return build_jikeyun_client_from_config(
            config=config,
            env=env,
            transport=jikeyun_transport,
        )
    raise ValueError(f"Unsupported source mode: {config.source.mode}")


def build_jikeyun_client_from_config(
    config: AppConfig,
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> JikeyunClient:
    """Builds a JackYun client from safe config and environment credentials."""

    source_env = env or os.environ
    credentials = JikeyunCredentials(
        app_key=_required_env(source_env, config.jikeyun.app_key_env),
        app_secret=_required_env(source_env, config.jikeyun.app_secret_env),
        # app_key="88026291",
        # app_secret="5401b92de3334150857739e615dbbceb",
    )
    # === MODIFIED START ===
    # 原因：仅在配置启用 RPA 时才加载 pyautogui 导出模块，避免默认运行受桌面环境影响。
    # 影响范围：吉客云客户端组装、RPA 实验模式。
    rpa_exporter = None
    if config.rpa.enabled:
        from infrastructure.db_to_xlsx import export_orders_to_xlsx

        rpa_exporter = export_orders_to_xlsx
    # === MODIFIED END ===
    return JikeyunClient(
        credentials=credentials,
        page_size=config.jikeyun.page_size,
        version=config.jikeyun.version,
        content_type=config.jikeyun.content_type,
        start_time_field=config.jikeyun.start_time_field,
        end_time_field=config.jikeyun.end_time_field,
        status_field=config.jikeyun.status_field,
        status_values=config.jikeyun.status_values,
        extra_params=config.jikeyun.extra_params,
        page_index_base=config.jikeyun.page_index_base,
        transport=transport or JikeyunHttpTransport(config.jikeyun.api_url),
        # === MODIFIED START ===
        # 原因：把配置化 RPA 导出和 XLSX 路径注入吉客云客户端，失败时通过统一日志记录 trace_id。
        # 影响范围：吉客云真实来源运行。
        rpa_exporter=rpa_exporter,
        xlsx_path=config.rpa.xlsx_path,
        log_info=log_info,
        log_error=log_error,
        # === MODIFIED END ===
    )


# === MODIFIED END ===


def build_mock_jikeyun_client(config: AppConfig) -> JikeyunClient:
    """Builds a mock JackYun client for local manual runs."""

    return JikeyunClient(
        credentials=JikeyunCredentials(
            app_key="LOCAL_APPKEY", app_secret="LOCAL_SECRET"
        ),
        page_size=100,
        transport=lambda request: JikeyunPageResult(
            items=tuple(_mock_raw_orders(config)),
            has_next=False,
        ),
    )


# === MODIFIED START ===
# 原因：文件上传客户端需要按配置构建。
# 影响范围：Pipeline 文件上传阶段。
def _build_upload_fn(
    config: AppConfig,
    env: Mapping[str, str] | None = None,
) -> Callable[[Path], str] | None:
    """Returns an upload function when upload is enabled, or None otherwise."""
    if not config.upload.enabled or not config.upload.api_url:
        return None

    client = FileUploadClient(
        api_url=config.upload.api_url,
        timeout_seconds=config.upload.timeout_seconds,
    )
    return client.upload


# === MODIFIED END ===
# === MODIFIED START ===
# 原因：吉客云认证只能从环境变量读取，不能写入配置或日志。
# 影响范围：真实吉客云任务运行。
def _required_env(env: Mapping[str, str], env_name: str) -> str:
    value = env.get(env_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Required environment variable is missing: {env_name}")
    return value.strip()


# === MODIFIED END ===


def summarize_result(result: PipelineRunResult) -> RunSummary:
    """Converts a pipeline result into a compact run summary."""

    # === MODIFIED START ===
    # 原因：推送群失败计入异常订单后，正常通过数需要扣除已进入异常的订单，避免重复统计。
    # 影响范围：RunSummary.passed_count/error_count 与前端任务统计。
    exception_order_nos = {
        exception_order.order_no for exception_order in result.exception_orders
    }
    passed_order_nos = {passed_order.order_no for passed_order in result.passed_orders}
    # === MODIFIED END ===
    return RunSummary(
        trace_id=result.task_context.trace_id,
        # === MODIFIED START ===
        # 原因：通过订单按最终未异常的订单去重统计。
        # 影响范围：RunSummary.passed_count。
        passed_count=len(passed_order_nos - exception_order_nos),
        # === MODIFIED END ===
        ignored_count=len(result.ignored_orders),
        # === MODIFIED START ===
        # 原因：异常订单数统计规则失败和推送群失败，不包含金蝶供应商资料缺失。
        # 影响范围：RunSummary.error_count 与前端任务异常统计。
        error_count=len(exception_order_nos),
        # === MODIFIED END ===
        delivery_count=len(result.deliveries),
        kingdee_tracking_id=result.kingdee_tracking_id,
        # === MODIFIED START ===
        # 原因：任务摘要需要带出状态和时间窗，供持久化与前端展示。
        # 影响范围：RunSummary 构建。
        task_name=result.task_context.task_name,
        created_at=result.task_context.created_at.isoformat(),
        window_start=result.task_context.window_start.isoformat(),
        window_end=result.task_context.window_end.isoformat(),
        push_status=result.push_status,
        kingdee_status=result.kingdee_status,
        failure_stage=result.failure_stage,
        failure_reason=result.failure_reason,
        # === MODIFIED END ===
    )


# === MODIFIED START ===
# 原因：可视化执行日志需要把 pipeline 结果转为业务人员可读的阶段记录。
# 影响范围：run_once 执行日志输出。
def _append_result_execution_logs(
    store: ExecutionLogStore, result: PipelineRunResult
) -> None:
    """Appends business-readable execution logs from a pipeline result."""

    task_context = result.task_context
    _append_execution_log(
        store,
        task_context,
        ExecutionLogStage.RULE,
        ExecutionLogResult.SUCCESS,
        "规则判断完成",
        impact=(
            f"规则通过 {len(result.passed_orders)} 单，忽略 {len(result.ignored_orders)} 单，"
            f"规则异常 {len(result.error_orders)} 单"
        ),
        suggestion=(
            "规则异常订单可在任务清单下载异常订单明细查看。"
            if result.error_orders
            else "规则阶段无需处理。"
        ),
        details={
            "passed_count": len(result.passed_orders),
            "ignored_count": len(result.ignored_orders),
            "rule_error_count": len(result.error_orders),
        },
    )
    _append_execution_log(
        store,
        task_context,
        ExecutionLogStage.FILE,
        ExecutionLogResult.SUCCESS if result.deliveries else ExecutionLogResult.SKIPPED,
        "推送文件处理完成" if result.deliveries else "没有生成推送文件",
        impact=f"成功推送批次对应文件 {len(result.deliveries)} 个",
        suggestion="如需核对使用者查看体验，可在任务清单下载正常推送订单明细。",
        details={"delivery_count": len(result.deliveries)},
    )
    _append_execution_log(
        store,
        task_context,
        ExecutionLogStage.MESSAGE,
        _push_execution_result(result.push_status),
        _push_execution_summary(result.push_status),
        impact=f"推送状态：{result.push_status.value}；成功推送批次 {len(result.deliveries)} 个",
        suggestion=_push_execution_suggestion(result),
        details={
            "push_status": result.push_status.value,
            "delivery_count": len(result.deliveries),
            "failure_stage": result.failure_stage,
            "failure_reason": result.failure_reason,
        },
    )
    _append_execution_log(
        store,
        task_context,
        ExecutionLogStage.KINGDEE,
        _kingdee_execution_result(result.kingdee_status),
        _kingdee_execution_summary(result.kingdee_status),
        impact=f"金蝶状态：{result.kingdee_status.value}",
        suggestion=_kingdee_execution_suggestion(result),
        details={
            "kingdee_status": result.kingdee_status.value,
            "kingdee_tracking_id": result.kingdee_tracking_id,
            "failure_stage": result.failure_stage,
            "failure_reason": result.failure_reason,
        },
    )


def _append_execution_log(
    store: ExecutionLogStore,
    task_context,
    stage: ExecutionLogStage,
    result: ExecutionLogResult,
    summary: str,
    impact: str = "",
    suggestion: str = "",
    details: dict[str, object] | None = None,
) -> None:
    """Appends one business-readable execution log with the task trace id."""

    store.append(
        ExecutionLogRecord(
            # === MODIFIED START ===
            # 原因：执行日志是过程记录，时间应表示该条日志写入时间，而不是整批任务创建时间。
            # 影响范围：执行日志页面时间线排序和展示。
            created_at=datetime.now().isoformat(),
            # === MODIFIED END ===
            trace_id=task_context.trace_id,
            task_name=task_context.task_name,
            stage=stage,
            result=result,
            summary=summary,
            impact=impact,
            suggestion=suggestion,
            details=details or {},
        )
    )


def _push_execution_result(status: PushStatus) -> ExecutionLogResult:
    """Maps push status to execution log result."""

    if status is PushStatus.SUCCESS:
        return ExecutionLogResult.SUCCESS
    if status is PushStatus.PARTIAL:
        return ExecutionLogResult.PARTIAL
    if status is PushStatus.FAILED:
        return ExecutionLogResult.FAILED
    return ExecutionLogResult.SKIPPED


def _kingdee_execution_result(status: KingdeeStatus) -> ExecutionLogResult:
    """Maps Kingdee status to execution log result."""

    if status is KingdeeStatus.SUCCESS:
        return ExecutionLogResult.SUCCESS
    if status is KingdeeStatus.FAILED:
        return ExecutionLogResult.FAILED
    return ExecutionLogResult.SKIPPED


def _task_execution_result(summary: RunSummary) -> ExecutionLogResult:
    """Builds the final task execution result."""

    if (
        summary.push_status is PushStatus.FAILED
        or summary.kingdee_status is KingdeeStatus.FAILED
    ):
        return ExecutionLogResult.FAILED
    if summary.push_status is PushStatus.PARTIAL or summary.error_count > 0:
        return ExecutionLogResult.PARTIAL
    return ExecutionLogResult.SUCCESS


def _push_execution_summary(status: PushStatus) -> str:
    """Builds a readable summary for the group message stage."""

    if status is PushStatus.SUCCESS:
        return "沟通群推送完成"
    if status is PushStatus.PARTIAL:
        return "沟通群部分推送成功"
    if status is PushStatus.FAILED:
        return "沟通群推送失败"
    return "没有需要推送的沟通群文件"


def _push_execution_suggestion(result: PipelineRunResult) -> str:
    """Builds a readable suggestion for the group message stage."""

    if result.push_status in (PushStatus.PARTIAL, PushStatus.FAILED):
        return "推送群失败会计入异常订单；请在任务清单下载异常订单明细，查看 MessagePush 记录。"
    if result.push_status is PushStatus.PENDING:
        return "无通过规则的订单时不需要推送沟通群。"
    return "沟通群推送阶段无需处理。"


def _kingdee_execution_summary(status: KingdeeStatus) -> str:
    """Builds a readable summary for the Kingdee stage."""

    if status is KingdeeStatus.SUCCESS:
        return "金蝶采购申请已提交"
    if status is KingdeeStatus.FAILED:
        return "金蝶采购申请提交失败"
    if status is KingdeeStatus.DISABLED:
        return "金蝶推送未启用，已跳过"
    return "没有提交金蝶采购申请"


def _kingdee_execution_suggestion(result: PipelineRunResult) -> str:
    """Builds a readable suggestion for the Kingdee stage."""

    if result.kingdee_status is KingdeeStatus.FAILED:
        return "检查 SKU-供应商对照、金蝶接口配置和返回错误；缺供应商不影响沟通群推送。"
    if result.kingdee_status is KingdeeStatus.DISABLED:
        return "当前按产品预设跳过金蝶；需要启用时在规则配置中心打开金蝶开关。"
    return "金蝶阶段无需处理。"


def _task_completion_suggestion(summary: RunSummary) -> str:
    """Builds a readable final task suggestion."""

    if summary.push_status in (PushStatus.PARTIAL, PushStatus.FAILED):
        return "优先处理推送群失败的异常订单，再决定是否重推。"
    if summary.error_count > 0:
        return "存在异常订单；请下载异常订单明细并按原因处理。"
    if summary.kingdee_status is KingdeeStatus.FAILED:
        return "订单已推送沟通群，但金蝶提交失败；请处理金蝶配置或供应商对照。"
    return "本次任务无需人工处理。"


def _safe_exception_reason(exc: Exception) -> str:
    """Builds a concise non-sensitive exception reason for execution logs."""

    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}: {message}"[:500]


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：补全异常订单的推送群名称、群主手机号和供应商名称，确保落盘 JSON 字段完整。
# 影响范围：exception_orders.json 输出与接口查询。
def _enrich_exception_orders(
    exception_orders: tuple[ExceptionOrder, ...] | list[ExceptionOrder],
    sku_group_map: dict,
    supplier_client,
) -> tuple[ExceptionOrder, ...]:
    """Fills group_name, owner_mobile and supplier_name for each exception order."""

    enriched: list[ExceptionOrder] = []
    for order in exception_orders:
        group_name = ""
        owner_mobile = ""
        info = sku_group_map.get(order.sku_code.strip())
        if info is not None and hasattr(info, "group_name"):
            group_name = getattr(info, "group_name", "")
            owner_mobile = getattr(info, "owner_mobile", "")
        supplier_name = supplier_client.get_supplier(order.sku_code.strip()) or ""
        if (
            group_name != order.group_name
            or owner_mobile != order.owner_mobile
            or supplier_name != order.supplier_name
        ):
            order = replace(
                order,
                group_name=group_name,
                owner_mobile=owner_mobile,
                supplier_name=supplier_name,
            )
        enriched.append(order)
    return tuple(enriched)


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：异常订单需要按厂家生成 error Excel 文件。
# 影响范围：/outputs/order_files/error/ 目录。
def _generate_error_files(
    exception_orders: tuple[ExceptionOrder, ...],
    output_dir: str | Path,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Groups exception orders by group_name and generates one error Excel per group."""
    if not exception_orders:
        return

    grouped: dict[str, list[ExceptionOrder]] = {}
    for order in exception_orders:
        key = order.group_name or "unknown"
        grouped.setdefault(key, []).append(order)

    generator = ExcelFileGenerator(output_dir=output_dir, clock=clock)
    for group_name, orders in sorted(grouped.items()):
        try:
            generated = generator.generate_error(
                group_name=group_name,
                exception_orders=tuple(orders),
            )
            log_info(
                "error_file_generated",
                {
                    "trace_id": "error-file",
                    "group_name": group_name,
                    "file_path": str(generated.file_path),
                    "row_count": generated.row_count,
                },
            )
        except Exception as exc:
            log_error(
                "error_file_generation_failed",
                {
                    "trace_id": "error-file",
                    "group_name": group_name,
                    "error_type": exc.__class__.__name__,
                    "reason": str(exc)[:200],
                },
            )


# === MODIFIED END ===


def _mock_raw_orders(config: AppConfig) -> list[dict[str, object]]:
    sku_group_map = config.rules.sku_group_map
    excluded_warehouses = config.rules.excluded_warehouses

    pass_sku = next(iter(sku_group_map), "SKU-PASS")
    # === MODIFIED START ===
    # 原因：SKU 服务规则已改为排除逻辑，mock 异常订单改由未配置群触发。
    # 影响范围：本地 mock-run 示例数据。
    unmapped_sku = "SKU-NO-GROUP"
    # === MODIFIED END ===
    ignored_warehouse = next(iter(excluded_warehouses), "WH-IGNORE")

    return [
        # 测试正常推送流程——sku="测试sku" 匹配 sku_group_map 中的 weworktest 群
        # _raw_order(
        #     order_no="JY202605189067",
        #     sku_code="测试sku",
        #     warehouse_code="WH-LOCAL",
        #     province="广东省",
        #     city="深圳市",
        # ),
        # 测试 sop 群推送流程——sku="测试sku-sop" 匹配 sku_group_map 中的 sop测试1 群
        _raw_order(
            order_no="JY202605189069",
            sku_code="测试sku-sop",
            warehouse_code="WH-LOCAL",
            province="广东省",
            city="深圳市",
        ),
        # 测试异常流程——未配置群的 SKU 被 GroupRule 拦截
        # _raw_order(
        #     order_no="JY202605189068",
        #     sku_code=unmapped_sku,
        #     warehouse_code="WH-LOCAL",
        #     province="广东省",
        #     city="深圳市",
        # ),
        # === MODIFIED START ===
        # 原因：测试 xlsx 兜底——delivery_order_no 命中 xlsx 真实订单编号，API 无收件人信息。
        # 影响范围：本地 mock-run 示例数据。
        # _raw_order(
        #     order_no="JY202605189067",
        #     sku_code="防晒服AMGB2377/白色/2XL",
        #     warehouse_code="WH-LOCAL",
        #     province="广东省",
        #     city="深圳市",
        #     delivery_order_no="JY2026051213434",
        #     receiver_name="",
        #     address="",
        #     phone="",
        # ),
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：测试极值兜底——API 和 xlsx 都没有收件人信息，最终显示"未提供"。
        # 影响范围：本地 mock-run 示例数据。
        # _raw_order(
        #     order_no="SO-LOCAL-NO-INFO",
        #     sku_code=pass_sku,
        #     warehouse_code="WH-LOCAL",
        #     province="广东省",
        #     city="深圳市",
        #     delivery_order_no="NOT-IN-XLSX",
        #     receiver_name="",
        #     address="",
        #     phone="",
        # ),
        # === MODIFIED END ===
    ]


def _raw_order(
    order_no: str,
    sku_code: str,
    warehouse_code: str,
    province: str,
    city: str,
    # === MODIFIED START ===
    # 原因：支持 mock 订单自定义 delivery_order_no 和收件人字段，测试 xlsx 兜底逻辑。
    # 影响范围：_mock_raw_orders 调用方。
    delivery_order_no: str | None = None,
    receiver_name: str = "Receiver",
    address: str = "Address",
    phone: str = "13800000000",
    # === MODIFIED END ===
) -> dict[str, object]:
    return {
        "order_no": order_no,
        "delivery_order_no": delivery_order_no or f"DO-{order_no}",
        "sku_code": sku_code,
        "goods_summary": f"Goods {sku_code}",
        "quantity": 1,
        "receiver_name": receiver_name,
        "address": address,
        "phone": phone,
        "logistics_company": "SF",
        "logistics_no": f"SF-{order_no}",
        "warehouse_code": warehouse_code,
        "warehouse_name": warehouse_code,
        "receiver_province": province,
        "receiver_city": city,
        "receiver_district": "",
    }
