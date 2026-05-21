from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.rules.region_rule import RestrictedRegion
from domain.sku_group_info import SkuGroupInfo


# === MODIFIED START ===
# 原因：支持配置 API 局部更新规则配置时校验可写字段。
# 影响范围：配置服务更新规则字段的白名单。
RULE_UPDATE_KEYS = {
    # === MODIFIED START ===
    # 原因：排除库房规则需要支持模块级启用开关，和排除 SKU 的配置粒度保持一致。
    # 影响范围：规则配置局部更新白名单。
    "excluded_warehouses_enabled",
    # === MODIFIED END ===
    "excluded_warehouses",
    # === MODIFIED START ===
    # 原因：SKU 规则从启用白名单修正为排除黑名单；enabled_skus 仅作为旧前端兼容输入。
    # 影响范围：规则配置局部更新字段白名单。
    "excluded_skus_enabled",
    "excluded_skus",
    "enabled_skus",
    # === MODIFIED END ===
    "restricted_regions",
    # === MODIFIED START ===
    # 原因：限发区域和 SKU 群配置需要支持模块级启用开关。
    # 影响范围：规则配置局部更新白名单。
    "restricted_regions_enabled",
    "sku_group_map_enabled",
    # === MODIFIED END ===
    "sku_group_map",
    # === MODIFIED START ===
    # 原因：个人顾客订单过滤规则支持模块级启用开关和 MULTI 后缀配置。
    # 影响范围：规则配置局部更新白名单。
    "personal_order_filter_enabled",
    "personal_order_suffix",
    "order_prefix_filter_enabled",
    "allowed_order_prefixes",
    # === MODIFIED END ===
}
# === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class TaskConfig:
    """Configuration for scheduled task creation."""

    name: str
    window_minutes: int


# === MODIFIED START ===
# 原因：第一版定时任务支持一个固定运行时间配置。
# 影响范围：配置加载、保存和调度器。
@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    """Configuration for the fixed daily scheduler."""

    enabled: bool
    run_at: str
    # === MODIFIED START ===
    # 原因：定时任务配置需要支持多条记录，并能独立持久化运行状态。
    # 影响范围：ScheduleConfig、Scheduler 状态、配置 API。
    schedule_id: str = "default"
    name: str = "默认定时任务"
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：后台常驻 tick loop 需要可配置检查间隔。
    # 影响范围：Scheduler loop 配置。
    check_interval_seconds: int = 60
    # === MODIFIED END ===
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：RPA 桌面导出需要独立开关，避免默认影响吉客云 OpenAPI 拉单。
# 影响范围：配置解析、任务组装、吉客云 XLSX 兜底补数。
@dataclass(frozen=True, slots=True)
class RpaConfig:
    """Configuration for optional desktop RPA order export."""

    enabled: bool
    xlsx_path: Path


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：订单来源需要支持 mock 与真实吉客云接口切换。
# 影响范围：任务运行数据源配置。
@dataclass(frozen=True, slots=True)
class OrderSourceConfig:
    """Configuration for the order source used by task runs."""

    mode: str
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：真实吉客云拉单需要配置网关、分页和时间字段，认证从环境变量读取。
# 影响范围：吉客云客户端构建。
@dataclass(frozen=True, slots=True)
class JikeyunConfig:
    """Configuration for JackYun order query integration."""

    api_url: str
    app_key_env: str
    app_secret_env: str
    # === MODIFIED START ===
    # 原因：吉客云公共请求参数需要版本号和返回格式，且不同租户可能存在差异。
    # 影响范围：吉客云客户端构建和配置序列化。
    version: str
    content_type: str
    # === MODIFIED END ===
    page_size: int
    start_time_field: str
    end_time_field: str
    status_field: str
    status_values: tuple[int | str, ...]
    # === MODIFIED START ===
    # 原因：吉客云订单查询业务参数仍待联调确认，需要预留配置化扩展入口。
    # 影响范围：吉客云请求业务参数组装。
    extra_params: dict[str, object]
    # === MODIFIED END ===
    page_index_base: int
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：金蝶采购申请提交需要支持本地 mock 与 HTTP 接口联调切换。
# 影响范围：配置加载、任务运行和金蝶基础设施适配。
@dataclass(frozen=True, slots=True)
class KingdeeConfig:
    """Configuration for Kingdee purchase request integration."""

    # === MODIFIED START ===
    # 原因：产品预设金蝶推送可单独启停，当前默认不启用。
    # 影响范围：配置解析、任务运行和前端配置回填。
    enabled: bool
    # === MODIFIED END ===
    mode: str
    api_url: str
    token_env: str
    timeout_seconds: float
    tracking_id_fields: tuple[str, ...]
    extra_headers: dict[str, str]
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：祺信群消息推送需要支持 mock 与真实 API 切换，凭据通过环境变量注入。
# 影响范围：配置加载、任务运行和消息适配器构建。
@dataclass(frozen=True, slots=True)
class QixinConfig:
    """Configuration for Qixin group message integration."""

    mode: str
    api_base_url: str
    caller_id: str
    secret_key_env: str
    userid_api_url: str
    timeout_seconds: float
    # === MODIFIED START ===
    # 原因：消息推送方式需要支持"文本链接推送"和"文件直推"两种模式。
    # 影响范围：QixinConfig、配置解析、祺信客户端构建。
    push_mode: str
    # === MODIFIED END ===
# === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """Configuration used to construct pure domain rules."""

    # === MODIFIED START ===
    # 原因：规则配置中心需要按模块控制排除库房是否参与规则判断。
    # 影响范围：RuleConfig、配置解析、规则引擎构建。
    excluded_warehouses_enabled: bool
    # === MODIFIED END ===
    excluded_warehouses: tuple[str, ...]
    # === MODIFIED START ===
    # 原因：SKU 规则实际是排除逻辑，不是启用逻辑。
    # 影响范围：规则配置模型和规则构建。
    excluded_skus_enabled: bool
    excluded_skus: tuple[str, ...]
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：规则配置中心需要按模块控制限发区域与 SKU 群配置是否参与规则判断。
    # 影响范围：RuleConfig、配置解析、规则引擎构建。
    restricted_regions_enabled: bool
    restricted_regions: tuple[RestrictedRegion, ...]
    sku_group_map_enabled: bool
    # === MODIFIED END ===
    sku_group_map: dict[str, SkuGroupInfo]
    # === MODIFIED START ===
    # 原因：个人顾客订单过滤规则需要模块级启用开关和 MULTI 后缀配置。
    # 影响范围：RuleConfig、配置解析、规则引擎构建。
    personal_order_filter_enabled: bool
    personal_order_suffix: str
    order_prefix_filter_enabled: bool
    allowed_order_prefixes: tuple[str, ...]
    # === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class MessageConfig:
    """Configuration for message sending retries."""

    max_attempts: int
    retry_interval_seconds: float


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Configuration for generated output paths."""

    order_file_dir: Path


@dataclass(frozen=True, slots=True)
class DownloadConfig:
    """Configuration for the signed order-file download endpoint."""

    base_url: str
    secret_key_env: str
    # === MODIFIED START ===
    # 原因：祺信文件直推模式需要知道文件的公网下载地址。
    # 影响范围：DownloadConfig、配置解析、GeneratedFile.file_url 注入。
    file_url: str | None = None
    # === MODIFIED END ===


# === MODIFIED START ===
# 原因：文件生成后需要上传到公网文件服务器，供群消息推送使用。
# 影响范围：UploadConfig、配置解析、Pipeline 推送阶段。
@dataclass(frozen=True, slots=True)
class UploadConfig:
    """Configuration for uploading generated files to a remote file server."""

    enabled: bool
    api_url: str
    timeout_seconds: float


# === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application configuration loaded from JSON."""

    task: TaskConfig
    # === MODIFIED START ===
    # 原因：应用配置需要携带固定时间调度设置。
    # 影响范围：AppConfig 和 API 配置返回。
    schedule: ScheduleConfig
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：规则配置中心需要维护多条定时任务配置。
    # 影响范围：AppConfig、配置解析/序列化、Scheduler API。
    schedules: tuple[ScheduleConfig, ...]
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：应用配置需要携带订单来源和吉客云接口设置。
    # 影响范围：AppConfig 和任务运行。
    source: OrderSourceConfig
    jikeyun: JikeyunConfig
    # === MODIFIED START ===
    # 原因：RPA 导出配置需要随应用配置一起传入任务组装层。
    # 影响范围：AppConfig 构造、配置解析、吉客云客户端组装。
    rpa: RpaConfig
    # === MODIFIED END ===
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：应用配置需要携带金蝶采购申请提交设置。
    # 影响范围：AppConfig 和任务运行。
    kingdee: KingdeeConfig
    # === MODIFIED END ===
    # === MODIFIED START ===
    # 原因：应用配置需要携带祺信消息推送设置。
    # 影响范围：AppConfig 和任务运行。
    qixin: QixinConfig
    # === MODIFIED END ===
    rules: RuleConfig
    message: MessageConfig
    output: OutputConfig
    download: DownloadConfig
    upload: UploadConfig


class ConfigService:
    """Loads and validates application configuration from JSON files."""

    def load(self, config_path: str | Path) -> AppConfig:
        path = Path(config_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return self.from_dict(data)

    # === MODIFIED START ===
    # 原因：支持接口层保存完整配置，避免 router 直接读写配置文件。
    # 影响范围：配置文件持久化能力。
    def save(self, config_path: str | Path, config: AppConfig) -> None:
        """Persists validated application configuration as JSON."""

        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(to_dict(config), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def replace(self, config_path: str | Path, data: dict[str, Any]) -> AppConfig:
        """Validates and replaces the complete application configuration."""

        config = self.from_dict(data)
        self.save(config_path, config)
        return config

    def update_rules(self, config_path: str | Path, updates: dict[str, Any]) -> AppConfig:
        """Validates and persists partial rule configuration updates."""

        unknown_keys = set(updates) - RULE_UPDATE_KEYS
        if unknown_keys:
            unknown_key_text = ", ".join(sorted(unknown_keys))
            raise ValueError(f"Unsupported rule config keys: {unknown_key_text}")

        path = Path(config_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data.setdefault("rules", {})
        if not isinstance(rules, dict):
            raise ValueError("rules must be an object")

        # === MODIFIED START ===
        # 原因：旧前端可能仍提交 enabled_skus；保存时迁移到 excluded_skus，避免继续扩散错误语义。
        # 影响范围：/config/rules 兼容写入。
        updates = dict(updates)
        if "enabled_skus" in updates and "excluded_skus" not in updates:
            updates["excluded_skus"] = updates["enabled_skus"]
        updates.pop("enabled_skus", None)
        # === MODIFIED END ===
        rules.update(updates)
        return self.replace(path, data)
    # === MODIFIED END ===

    def from_dict(self, data: dict[str, Any]) -> AppConfig:
        task = data.get("task", {})
        # === MODIFIED START ===
        # 原因：兼容旧配置文件，缺省时调度器不自动运行。
        # 影响范围：配置解析。
        schedule = data.get("schedule", {})
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：兼容旧配置，缺省时继续使用 mock 订单来源。
        # 影响范围：配置解析。
        source = data.get("source", {})
        jikeyun = data.get("jikeyun", {})
        # === MODIFIED START ===
        # 原因：RPA 配置需要独立解析，默认关闭以免影响既有取数链路。
        # 影响范围：配置解析、吉客云客户端组装。
        rpa = data.get("rpa", {})
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：解析金蝶采购申请提交配置。
        # 影响范围：任务运行金蝶提交通道。
        kingdee = data.get("kingdee", {})
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：解析祺信消息推送配置。
        # 影响范围：消息发送通道构建。
        qixin = data.get("qixin", {})
        # === MODIFIED END ===
        rules = data.get("rules", {})
        message = data.get("message", {})
        output = data.get("output", {})

        task_config = TaskConfig(
            name=_required_string(task, "name", "task.name"),
            window_minutes=_positive_int(task, "window_minutes", "task.window_minutes"),
        )
        # === MODIFIED START ===
        # 原因：定时任务配置从单条 schedule 升级为多条 schedules，并兼容旧配置。
        # 影响范围：配置解析、Scheduler、配置 API。
        schedules_config = _schedule_configs(data)
        schedule_config = schedules_config[0]
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：解析订单来源和吉客云接口配置。
        # 影响范围：任务运行数据源。
        source_config = OrderSourceConfig(
            mode=_source_mode(source, "mode", "mock", "source.mode"),
        )
        jikeyun_config = JikeyunConfig(
            api_url=_optional_string_with_default(
                jikeyun,
                "api_url",
                "https://open.jackyun.com/open/openapi/do",
                "jikeyun.api_url",
            ),
            app_key_env=_optional_string_with_default(
                jikeyun,
                "app_key_env",
                "JIKEYUN_APPKEY",
                "jikeyun.app_key_env",
            ),
            app_secret_env=_optional_string_with_default(
                jikeyun,
                "app_secret_env",
                "JIKEYUN_APP_SECRET",
                "jikeyun.app_secret_env",
            ),
            # === MODIFIED START ===
            # 原因：解析吉客云公共请求参数版本号和返回格式。
            # 影响范围：吉客云客户端构建。
            version=_optional_string_with_default(
                jikeyun,
                "version",
                "v1.0",
                "jikeyun.version",
            ),
            content_type=_optional_string_with_default(
                jikeyun,
                "content_type",
                "JSON",
                "jikeyun.content_type",
            ),
            # === MODIFIED END ===
            page_size=_optional_positive_int(jikeyun, "page_size", 100, "jikeyun.page_size"),
            start_time_field=_optional_string_with_default(
                jikeyun,
                "start_time_field",
                "startModifyTime",
                "jikeyun.start_time_field",
            ),
            end_time_field=_optional_string_with_default(
                jikeyun,
                "end_time_field",
                "endModifyTime",
                "jikeyun.end_time_field",
            ),
            status_field=_optional_string_with_default(
                jikeyun,
                "status_field",
                "orderStatusList",
                "jikeyun.status_field",
            ),
            # === MODIFIED START ===
            # 原因：真实吉客云 wms.order.query-info.page.v2 使用整数状态码数组 orderStatusList。
            # 影响范围：吉客云配置解析。
            status_values=tuple(
                _status_value_list(
                    jikeyun,
                    "status_values",
                    [0, 1, 3, 4, 5, 6, 15],
                    "jikeyun.status_values",
                )
            ),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：解析额外业务参数，避免把未确认的接口字段写死进代码。
            # 影响范围：吉客云请求业务参数。
            extra_params=_object_map(jikeyun, "extra_params", "jikeyun.extra_params"),
            # === MODIFIED END ===
            page_index_base=_non_negative_int(jikeyun, "page_index_base", 0, "jikeyun.page_index_base"),
        )
        # === MODIFIED START ===
        # 原因：RPA 导出的启停和 XLSX 路径需要配置化，默认关闭保持既有行为。
        # 影响范围：配置解析、吉客云任务运行。
        rpa_config = RpaConfig(
            enabled=_optional_bool(rpa, "enabled", False, "rpa.enabled"),
            xlsx_path=Path(
                _optional_string_with_default(
                    rpa,
                    "xlsx_path",
                    str(Path("input") / "销售单查询.xlsx"),
                    "rpa.xlsx_path",
                )
            ),
        )
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：解析金蝶接口模式、地址、鉴权环境变量和追踪号字段。
        # 影响范围：金蝶服务构建。
        kingdee_enabled = _optional_bool(kingdee, "enabled", False, "kingdee.enabled")
        kingdee_mode = _integration_mode(kingdee, "mode", "mock", "kingdee.mode")
        kingdee_api_url = _optional_blankable_string(kingdee, "api_url")
        # === MODIFIED START ===
        # 原因：金蝶未启用时允许预留 http 模式但暂不要求接口地址。
        # 影响范围：金蝶配置校验。
        if kingdee_enabled and kingdee_mode == "http" and not kingdee_api_url:
            raise ValueError("kingdee.api_url must be a non-empty string when kingdee.mode is http")
        # === MODIFIED END ===
        kingdee_config = KingdeeConfig(
            enabled=kingdee_enabled,
            mode=kingdee_mode,
            api_url=kingdee_api_url,
            token_env=_optional_string_with_default(
                kingdee,
                "token_env",
                "KINGDEE_TOKEN",
                "kingdee.token_env",
            ),
            timeout_seconds=_optional_positive_number(
                kingdee,
                "timeout_seconds",
                30,
                "kingdee.timeout_seconds",
            ),
            tracking_id_fields=tuple(
                _string_list_with_default(
                    kingdee,
                    "tracking_id_fields",
                    ["tracking_id", "trackingId", "id", "bill_no", "billNo", "number"],
                    "kingdee.tracking_id_fields",
                )
            ),
            extra_headers=_string_map_with_field_name(
                kingdee,
                "extra_headers",
                "kingdee.extra_headers",
            ),
        )
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：解析祺信消息推送接口模式、地址和凭据环境变量。
        # 影响范围：消息发送通道构建。
        qixin_mode = _optional_string_with_default(qixin, "mode", "mock", "qixin.mode")
        if qixin_mode not in {"mock", "qixin"}:
            raise ValueError("qixin.mode must be one of: mock, qixin")
        qixin_config = QixinConfig(
            mode=qixin_mode,
            api_base_url=_optional_blankable_string(qixin, "api_base_url"),
            caller_id=_optional_blankable_string(qixin, "caller_id"),
            secret_key_env=_optional_string_with_default(
                qixin, "secret_key_env", "QIXIN_SECRET_KEY", "qixin.secret_key_env"
            ),
            userid_api_url=_optional_string_with_default(
                qixin,
                "userid_api_url",
                "http://mengyang.renruikeji.cn/api/userid",
                "qixin.userid_api_url",
            ),
            timeout_seconds=_optional_positive_number(
                qixin, "timeout_seconds", 30, "qixin.timeout_seconds"
            ),
            # === MODIFIED START ===
            # 原因：解析祺信消息推送方式，支持"文本链接推送"和"文件直推"两种模式。
            # 影响范围：祺信客户端构建和消息发送。
            push_mode=_optional_string_with_default(qixin, "push_mode", "link", "qixin.push_mode"),
            # === MODIFIED END ===
        )
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：多个规则模块新增启用开关，解析前先标准化配置内容以复用默认启用判断。
        # 影响范围：规则配置解析。
        excluded_warehouses = tuple(_string_list(rules, "excluded_warehouses"))
        restricted_regions = tuple(_restricted_regions(rules.get("restricted_regions", [])))
        sku_group_map = _sku_group_map(rules, "sku_group_map")
        # === MODIFIED END ===
        rule_config = RuleConfig(
            # === MODIFIED START ===
            # 原因：排除库房模块新增总开关；旧配置若已有库房列表则默认保持启用。
            # 影响范围：规则配置解析。
            excluded_warehouses_enabled=_optional_bool(
                rules,
                "excluded_warehouses_enabled",
                bool(excluded_warehouses),
                "rules.excluded_warehouses_enabled",
            ),
            excluded_warehouses=excluded_warehouses,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：SKU 排除模块新增总开关；旧配置若已有 excluded_skus 列表则默认保持启用。
            # 影响范围：规则配置解析。
            excluded_skus_enabled=_optional_bool(
                rules,
                "excluded_skus_enabled",
                "excluded_skus" in rules and bool(rules.get("excluded_skus")),
                "rules.excluded_skus_enabled",
            ),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：SKU 规则从 enabled_skus 迁移到 excluded_skus，同时兼容旧配置文件。
            # 影响范围：规则配置解析。
            excluded_skus=tuple(
                _string_list_with_legacy(
                    rules,
                    "excluded_skus",
                    "enabled_skus",
                    "rules.excluded_skus",
                )
            ),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：限发区域和 SKU 群配置新增模块级启用开关；旧配置若已有对应内容则默认保持启用。
            # 影响范围：规则配置解析。
            restricted_regions_enabled=_optional_bool(
                rules,
                "restricted_regions_enabled",
                bool(restricted_regions),
                "rules.restricted_regions_enabled",
            ),
            restricted_regions=restricted_regions,
            sku_group_map_enabled=_optional_bool(
                rules,
                "sku_group_map_enabled",
                bool(sku_group_map),
                "rules.sku_group_map_enabled",
            ),
            sku_group_map=sku_group_map,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：解析个人顾客订单过滤规则配置。
            # 影响范围：RuleConfig 构造。
            personal_order_filter_enabled=_optional_bool(
                rules,
                "personal_order_filter_enabled",
                True,
                "rules.personal_order_filter_enabled",
            ),
            personal_order_suffix=_optional_string_with_default(
                rules,
                "personal_order_suffix",
                "-MULTI",
                "rules.personal_order_suffix",
            ),
            order_prefix_filter_enabled=_optional_bool(
                rules,
                "order_prefix_filter_enabled",
                True,
                "rules.order_prefix_filter_enabled",
            ),
            allowed_order_prefixes=tuple(
                _string_list(rules, "allowed_order_prefixes")
            ),
            # === MODIFIED END ===
        )
        message_config = MessageConfig(
            max_attempts=_positive_int(message, "max_attempts", "message.max_attempts"),
            retry_interval_seconds=_non_negative_number(
                message,
                "retry_interval_seconds",
                "message.retry_interval_seconds",
            ),
        )
        output_config = OutputConfig(
            order_file_dir=Path(_required_string(output, "order_file_dir", "output.order_file_dir")),
        )
        download = data.get("download", {})
        download_config = DownloadConfig(
            base_url=_optional_blankable_string(download, "base_url"),
            secret_key_env=_optional_string_with_default(
                download, "secret_key_env", "DOWNLOAD_SECRET_KEY", "download.secret_key_env"
            ),
            # === MODIFIED START ===
            # 原因：祺信文件直推模式需要知道文件的公网下载地址，优先读取 download.file_url。
            # 影响范围：DownloadConfig 初始化、GeneratedFile.file_url 注入。
            file_url=_optional_blankable_string(download, "file_url") or None,
            # === MODIFIED END ===
        )
        # === MODIFIED START ===
        # 原因：文件上传到公网文件服务器供群消息使用。
        # 影响范围：UploadConfig 初始化、Pipeline 推送阶段。
        upload = data.get("upload", {})
        upload_config = UploadConfig(
            enabled=_optional_bool(upload, "enabled", False, "upload.enabled"),
            api_url=_optional_blankable_string(upload, "api_url"),
            timeout_seconds=_optional_positive_number(
                upload, "timeout_seconds", 30, "upload.timeout_seconds"
            ),
        )
        # === MODIFIED END ===
        return AppConfig(
            task=task_config,
            # === MODIFIED START ===
            # 原因：返回调度配置给应用层。
            # 影响范围：AppConfig 构造。
            schedule=schedule_config,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：返回多条定时任务配置给应用层和配置 API。
            # 影响范围：AppConfig 构造。
            schedules=schedules_config,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：返回订单来源和吉客云配置给应用层。
            # 影响范围：AppConfig 构造。
            source=source_config,
            jikeyun=jikeyun_config,
            # === MODIFIED START ===
            # 原因：把 RPA 配置交给任务组装层决定是否注入桌面导出能力。
            # 影响范围：AppConfig 构造、吉客云客户端组装。
            rpa=rpa_config,
            # === MODIFIED END ===
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：返回金蝶接口配置给应用层。
            # 影响范围：AppConfig 构造。
            kingdee=kingdee_config,
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：返回祺信消息推送配置给应用层。
            # 影响范围：AppConfig 构造。
            qixin=qixin_config,
            # === MODIFIED END ===
            rules=rule_config,
            message=message_config,
            output=output_config,
            download=download_config,
            upload=upload_config,
        )


def _required_string(data: dict[str, Any], key: str, field_name: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(data: dict[str, Any], key: str, field_name: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


# === MODIFIED START ===
# 原因：调度配置需要校验布尔开关和 HH:MM 时间。
# 影响范围：配置解析辅助函数。
def _optional_bool(data: dict[str, Any], key: str, default: bool, field_name: str) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _time_string(data: dict[str, Any], key: str, default: str, field_name: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a HH:MM string")

    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"{field_name} must be a HH:MM string")

    hour_text, minute_text = parts
    if not hour_text.isdigit() or not minute_text.isdigit():
        raise ValueError(f"{field_name} must be a HH:MM string")

    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"{field_name} must be a valid HH:MM time")

    return f"{hour:02d}:{minute:02d}"


# === MODIFIED START ===
# 原因：定时任务配置需要从单条 schedule 升级为多条 schedules，并校验唯一编码。
# 影响范围：配置解析辅助函数。
def _schedule_configs(data: dict[str, Any]) -> tuple[ScheduleConfig, ...]:
    schedules_value = data.get("schedules")
    if schedules_value is None:
        legacy_schedule = data.get("schedule", {})
        if not isinstance(legacy_schedule, dict):
            raise ValueError("schedule must be an object")
        return (
            _schedule_config(
                legacy_schedule,
                field_name="schedule",
                default_schedule_id="default",
                default_name="默认定时任务",
            ),
        )

    if not isinstance(schedules_value, list):
        raise ValueError("schedules must be a list")
    if not schedules_value:
        raise ValueError("schedules must contain at least one item")

    result: list[ScheduleConfig] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(schedules_value):
        if not isinstance(item, dict):
            raise ValueError("schedules items must be objects")
        schedule = _schedule_config(
            item,
            field_name=f"schedules[{index}]",
            default_schedule_id=f"schedule-{index + 1:02d}",
            default_name=f"定时任务{index + 1}",
        )
        if schedule.schedule_id in seen_ids:
            raise ValueError("schedules.schedule_id must be unique")
        seen_ids.add(schedule.schedule_id)
        result.append(schedule)
    return tuple(result)


def _schedule_config(
    data: dict[str, Any],
    field_name: str,
    default_schedule_id: str,
    default_name: str,
) -> ScheduleConfig:
    return ScheduleConfig(
        enabled=_optional_bool(data, "enabled", False, f"{field_name}.enabled"),
        run_at=_time_string(data, "run_at", "09:00", f"{field_name}.run_at"),
        schedule_id=_optional_string_with_default(
            data,
            "schedule_id",
            default_schedule_id,
            f"{field_name}.schedule_id",
        ),
        name=_optional_string_with_default(
            data,
            "name",
            default_name,
            f"{field_name}.name",
        ),
        check_interval_seconds=_optional_positive_int(
            data,
            "check_interval_seconds",
            60,
            f"{field_name}.check_interval_seconds",
        ),
    )
# === MODIFIED END ===


def _optional_positive_int(
    data: dict[str, Any],
    key: str,
    default: int,
    field_name: str,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int(
    data: dict[str, Any],
    key: str,
    default: int,
    field_name: str,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_string_with_default(
    data: dict[str, Any],
    key: str,
    default: str,
    field_name: str,
) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _source_mode(data: dict[str, Any], key: str, default: str, field_name: str) -> str:
    value = _optional_string_with_default(data, key, default, field_name)
    allowed_modes = {"mock", "jikeyun"}
    if value not in allowed_modes:
        allowed_text = ", ".join(sorted(allowed_modes))
        raise ValueError(f"{field_name} must be one of: {allowed_text}")
    return value


# === MODIFIED START ===
# 原因：金蝶等外部集成需要统一校验 mock/http 模式。
# 影响范围：配置解析辅助函数。
def _integration_mode(data: dict[str, Any], key: str, default: str, field_name: str) -> str:
    value = _optional_string_with_default(data, key, default, field_name)
    allowed_modes = {"mock", "http"}
    if value not in allowed_modes:
        allowed_text = ", ".join(sorted(allowed_modes))
        raise ValueError(f"{field_name} must be one of: {allowed_text}")
    return value
# === MODIFIED END ===


def _non_negative_number(data: dict[str, Any], key: str, field_name: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative number")
    return float(value)


# === MODIFIED START ===
# 原因：金蝶 HTTP 超时配置需要正数但可缺省。
# 影响范围：配置解析辅助函数。
def _optional_positive_number(
    data: dict[str, Any],
    key: str,
    default: float,
    field_name: str,
) -> float:
    value = data.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return float(value)
# === MODIFIED END ===


def _string_list(data: dict[str, Any], key: str, field_name: str | None = None) -> list[str]:
    value = data.get(key, [])
    display_name = field_name or f"rules.{key}"
    if not isinstance(value, list):
        raise ValueError(f"{display_name} must be a list")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{display_name} must contain non-empty strings")
        result.append(item.strip())
    return result


# === MODIFIED START ===
# 原因：SKU 排除配置需要从旧 enabled_skus 字段平滑迁移到 excluded_skus。
# 影响范围：配置解析辅助函数。
def _string_list_with_legacy(
    data: dict[str, Any],
    key: str,
    legacy_key: str,
    field_name: str,
) -> list[str]:
    """Reads a string list from the primary key, falling back to one legacy key."""

    if key in data:
        return _string_list(data, key, field_name)
    if legacy_key in data:
        return _string_list(data, legacy_key, field_name)
    return []
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：吉客云订单状态配置需要支持整数状态码数组，而不是旧版中文字符串状态。
# 影响范围：JikeyunConfig.status_values 配置解析。
def _status_value_list(
    data: dict[str, Any],
    key: str,
    default: list[int | str],
    field_name: str,
) -> list[int | str]:
    value = data.get(key, default)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")

    result: list[int | str] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{field_name} must contain integers or non-empty strings")
        if isinstance(item, int):
            result.append(item)
            continue
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
            continue
        raise ValueError(f"{field_name} must contain integers or non-empty strings")
    return result
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：金蝶返回追踪号候选字段需要可配置且有默认值。
# 影响范围：配置解析辅助函数。
def _string_list_with_default(
    data: dict[str, Any],
    key: str,
    default: list[str],
    field_name: str,
) -> list[str]:
    if key not in data:
        return list(default)
    return _string_list(data, key, field_name)
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：吉客云业务参数待联调确认，需要支持 JSON-safe 配置对象透传。
# 影响范围：配置解析和吉客云请求组装。
def _object_map(data: dict[str, Any], key: str, field_name: str) -> dict[str, object]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")

    result: dict[str, object] = {}
    for map_key, map_value in value.items():
        if not isinstance(map_key, str) or not map_key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not _is_json_safe_value(map_value):
            raise ValueError(f"{field_name}.{map_key} must be JSON-safe")
        result[map_key.strip()] = map_value
    return result


def _is_json_safe_value(value: Any) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_safe_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_safe_value(item) for key, item in value.items())
    return False
# === MODIFIED END ===


def _string_map(data: dict[str, Any], key: str) -> dict[str, str]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"rules.{key} must be an object")

    result: dict[str, str] = {}
    for map_key, map_value in value.items():
        if not isinstance(map_key, str) or not map_key.strip():
            raise ValueError(f"rules.{key} keys must be non-empty strings")
        if not isinstance(map_value, str) or not map_value.strip():
            raise ValueError(f"rules.{key} values must be non-empty strings")
        result[map_key.strip()] = map_value.strip()
    return result


def _sku_group_map(data: dict[str, Any], key: str) -> dict[str, SkuGroupInfo]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"rules.{key} must be an object")

    result: dict[str, SkuGroupInfo] = {}
    for map_key, map_value in value.items():
        if not isinstance(map_key, str) or not map_key.strip():
            raise ValueError(f"rules.{key} keys must be non-empty strings")
        sku_code = map_key.strip()

        if isinstance(map_value, str):
            result[sku_code] = SkuGroupInfo(
                group_name=map_value.strip(),
                owner_mobile="",
                user_id="",
            )
        elif isinstance(map_value, dict):
            group_name = map_value.get("group_name", "")
            owner_mobile = map_value.get("owner_mobile", "")
            user_id = map_value.get("user_id", "")
            if not isinstance(group_name, str):
                raise ValueError(f"rules.{key}.{sku_code}.group_name must be a string")
            if not isinstance(owner_mobile, str):
                raise ValueError(f"rules.{key}.{sku_code}.owner_mobile must be a string")
            if not isinstance(user_id, str):
                raise ValueError(f"rules.{key}.{sku_code}.user_id must be a string")
            result[sku_code] = SkuGroupInfo(
                group_name=group_name.strip(),
                owner_mobile=owner_mobile.strip(),
                user_id=user_id.strip(),
            )
        else:
            raise ValueError(f"rules.{key}.{sku_code} must be a string or object")
    return result


# === MODIFIED START ===
# 原因：金蝶 HTTP 额外 header 需要专用字段名报错。
# 影响范围：配置解析辅助函数。
def _string_map_with_field_name(data: dict[str, Any], key: str, field_name: str) -> dict[str, str]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")

    result: dict[str, str] = {}
    for map_key, map_value in value.items():
        if not isinstance(map_key, str) or not map_key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(map_value, str) or not map_value.strip():
            raise ValueError(f"{field_name} values must be non-empty strings")
        result[map_key.strip()] = map_value.strip()
    return result
# === MODIFIED END ===


def _restricted_regions(value: Any) -> list[RestrictedRegion]:
    if not isinstance(value, list):
        raise ValueError("rules.restricted_regions must be a list")

    regions: list[RestrictedRegion] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("rules.restricted_regions items must be objects")

        regions.append(
            RestrictedRegion(
                sku_code=_required_string(item, "sku_code", "rules.restricted_regions.sku_code"),
                province=_required_string(item, "province", "rules.restricted_regions.province"),
                city=_optional_string(item, "city"),
                district=_optional_string(item, "district"),
            )
        )
    return regions


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when provided")
    return value.strip()


# === MODIFIED START ===
# 原因：金蝶 mock 模式允许 api_url 留空，http 模式再做非空校验。
# 影响范围：金蝶配置解析。
def _optional_blankable_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：配置保存时需要把 dataclass 配置转换回稳定 JSON 结构。
# 影响范围：配置接口返回与落盘格式。
def to_dict(config: AppConfig) -> dict[str, object]:
    """Converts AppConfig into JSON-compatible configuration data."""

    return {
        "task": {
            "name": config.task.name,
            "window_minutes": config.task.window_minutes,
        },
        # === MODIFIED START ===
        # 原因：配置 API 和落盘格式需要输出固定时间调度配置。
        # 影响范围：配置序列化。
        "schedule": {
            "schedule_id": config.schedule.schedule_id,
            "name": config.schedule.name,
            "enabled": config.schedule.enabled,
            "run_at": config.schedule.run_at,
            # === MODIFIED START ===
            # 原因：配置 API 需要返回后台 Scheduler 检查间隔。
            # 影响范围：配置序列化。
            "check_interval_seconds": config.schedule.check_interval_seconds,
            # === MODIFIED END ===
        },
        # === MODIFIED START ===
        # 原因：配置 API 和落盘格式需要输出多条定时任务配置。
        # 影响范围：配置序列化、规则配置中心回填。
        "schedules": [
            {
                "schedule_id": schedule.schedule_id,
                "name": schedule.name,
                "enabled": schedule.enabled,
                "run_at": schedule.run_at,
                "check_interval_seconds": schedule.check_interval_seconds,
            }
            for schedule in config.schedules
        ],
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：配置 API 需要输出订单来源和吉客云接口配置。
        # 影响范围：配置序列化。
        "source": {
            "mode": config.source.mode,
        },
        "jikeyun": {
            "api_url": config.jikeyun.api_url,
            "app_key_env": config.jikeyun.app_key_env,
            "app_secret_env": config.jikeyun.app_secret_env,
            # === MODIFIED START ===
            # 原因：配置返回需要包含吉客云公共请求参数。
            # 影响范围：/config 响应和配置落盘。
            "version": config.jikeyun.version,
            "content_type": config.jikeyun.content_type,
            # === MODIFIED END ===
            "page_size": config.jikeyun.page_size,
            "start_time_field": config.jikeyun.start_time_field,
            "end_time_field": config.jikeyun.end_time_field,
            "status_field": config.jikeyun.status_field,
            "status_values": list(config.jikeyun.status_values),
            # === MODIFIED START ===
            # 原因：配置返回需要保留吉客云额外业务参数。
            # 影响范围：/config 响应和配置落盘。
            "extra_params": dict(config.jikeyun.extra_params),
            # === MODIFIED END ===
            "page_index_base": config.jikeyun.page_index_base,
        },
        # === MODIFIED START ===
        # 原因：配置 API 需要输出 RPA 桌面导出开关和 XLSX 路径。
        # 影响范围：/config 响应和配置落盘。
        "rpa": {
            "enabled": config.rpa.enabled,
            "xlsx_path": str(config.rpa.xlsx_path),
        },
        # === MODIFIED END ===
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：配置 API 需要输出金蝶采购申请提交配置。
        # 影响范围：/config 响应和配置落盘。
        "kingdee": {
            # === MODIFIED START ===
            # 原因：配置 API 需要返回金蝶推送启用开关。
            # 影响范围：/config 响应和配置落盘。
            "enabled": config.kingdee.enabled,
            # === MODIFIED END ===
            "mode": config.kingdee.mode,
            "api_url": config.kingdee.api_url,
            "token_env": config.kingdee.token_env,
            "timeout_seconds": config.kingdee.timeout_seconds,
            "tracking_id_fields": list(config.kingdee.tracking_id_fields),
            "extra_headers": dict(config.kingdee.extra_headers),
        },
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：配置 API 需要输出祺信消息推送配置。
        # 影响范围：/config 响应和配置落盘。
        "qixin": {
            "mode": config.qixin.mode,
            "api_base_url": config.qixin.api_base_url,
            "caller_id": config.qixin.caller_id,
            "secret_key_env": config.qixin.secret_key_env,
            "userid_api_url": config.qixin.userid_api_url,
            "timeout_seconds": config.qixin.timeout_seconds,
            "push_mode": config.qixin.push_mode,
        },
        # === MODIFIED END ===
        "rules": {
            # === MODIFIED START ===
            # 原因：配置 API 需要返回排除库房模块开关，供规则配置中心回填。
            # 影响范围：config 响应和配置落盘。
            "excluded_warehouses_enabled": config.rules.excluded_warehouses_enabled,
            # === MODIFIED END ===
            "excluded_warehouses": list(config.rules.excluded_warehouses),
            # === MODIFIED START ===
            # 原因：配置输出改为 SKU 排除模块开关与排除列表，避免前端继续展示启用白名单语义。
            # 影响范围：/config 响应和配置落盘。
            "excluded_skus_enabled": config.rules.excluded_skus_enabled,
            "excluded_skus": list(config.rules.excluded_skus),
            # === MODIFIED END ===
            # === MODIFIED START ===
            # 原因：配置 API 需要返回限发区域和 SKU 群配置模块开关，供规则配置中心回填。
            # 影响范围：config 响应和配置落盘。
            "restricted_regions_enabled": config.rules.restricted_regions_enabled,
            "restricted_regions": [
            # === MODIFIED END ===
                {
                    "sku_code": region.sku_code,
                    "province": region.province,
                    "city": region.city,
                    "district": region.district,
                }
                for region in config.rules.restricted_regions
            ],
            # === MODIFIED START ===
            # 原因：配置 API 需要返回 SKU 群配置模块开关，供规则配置中心回填。
            # 影响范围：config 响应和配置落盘。
            "sku_group_map_enabled": config.rules.sku_group_map_enabled,
            # === MODIFIED END ===
            "sku_group_map": {
                sku: {
                    "group_name": info.group_name,
                    "owner_mobile": info.owner_mobile,
                    "user_id": info.user_id,
                }
                for sku, info in config.rules.sku_group_map.items()
            },
            # === MODIFIED START ===
            # 原因：配置 API 需要返回个人顾客订单过滤规则配置。
            # 影响范围：config 响应和配置落盘。
            "personal_order_filter_enabled": config.rules.personal_order_filter_enabled,
            "personal_order_suffix": config.rules.personal_order_suffix,
            "order_prefix_filter_enabled": config.rules.order_prefix_filter_enabled,
            "allowed_order_prefixes": list(config.rules.allowed_order_prefixes),
            # === MODIFIED END ===
        },
        "message": {
            "max_attempts": config.message.max_attempts,
            "retry_interval_seconds": config.message.retry_interval_seconds,
        },
        "output": {
            "order_file_dir": str(config.output.order_file_dir),
        },
        "download": {
            "base_url": config.download.base_url,
            "secret_key_env": config.download.secret_key_env,
            "file_url": config.download.file_url,
        },
        "upload": {
            "enabled": config.upload.enabled,
            "api_url": config.upload.api_url,
            "timeout_seconds": config.upload.timeout_seconds,
        },
    }
# === MODIFIED END ===
