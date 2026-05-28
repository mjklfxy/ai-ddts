# AI-DDTS — 订单自动分发推送系统

## 项目概述

AI-DDTS 是订单自动处理流水线：从吉客云 ERP 拉取销售单 → 规则引擎过滤 → 按业务群拆分 → 生成 Excel → 上传文件服务器 → 通过祺信 API 推送到企业微信群。

核心流程：
```
吉客云 OpenAPI 拉单 → 规则引擎过滤 → 按群拆分 → 生成 Excel → 上传 → 推送企业微信群
```

外部系统：
- **吉客云（JackYun）** — 电商 ERP，订单数据源，OpenAPI + HMAC-MD5 签名
- **祺信（Qixin）** — 企业微信消息推送，HMAC-SHA256 签名
- **金蝶（Kingdee）** — 财务系统，可选采购单提交
- **云仓** — 供应商数据同步

---

## Python 环境（强制）

- **必须使用虚拟环境**：所有 `python`、`pip`、`pytest` 命令必须在虚拟环境中执行，禁止直接使用系统 Python
- 项目使用 `uv` 管理依赖，优先使用 `uv run` 或激活 `.venv` 后执行
- Python 版本：3.12+（pyproject.toml 要求 `>=3.12`）
- 安装依赖：`uv sync`
- 运行测试：`uv run python -m pytest tests/ -v`
- 运行应用：`uv run uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory`
- CLI 入口：`uv run python main.py`

---

## 分层架构（强制）

依赖方向：`domain → application → infrastructure → interfaces`，只能单向向下。

| 层 | 目录 | 职责 |
|---|---|---|
| domain | `domain/` | 纯业务规则、枚举、值对象，**不得依赖 infrastructure** |
| application | `application/` | 流程编排、调度、配置、持久化 |
| infrastructure | `infrastructure/` | HTTP 客户端、RPA、消息适配器、外部 API |
| interfaces | `interfaces/` | FastAPI 路由 + 静态前端，**只做路由，不含业务逻辑** |
| shared | `shared/` | 日志、环境变量工具 |

关键约束：
- `pipeline.py` 只编排流程，不含业务逻辑
- `interfaces/app.py` 只做路由，不含业务逻辑
- 所有业务规则必须继承 `OrderRule`，放在 `domain/rules/` 下

---

## 目录结构

| 目录 | 用途 |
|---|---|
| `application/` | 应用层：pipeline、scheduler、config_service、manual_runner、task_service、file_generator、order_splitter、各种 store |
| `config/` | 配置文件：`config.json`（默认）、`config.dev.json`、`config_prod.json`（不提交 git） |
| `domain/` | 领域层：rule_engine、enums（rule/status/execution_log/exception）、rules（warehouse/sku/region/group/customer_type/order_prefix/supplier/special_sku） |
| `infrastructure/` | 基础设施：jikeyun_client、qixin_client、message_adapter、cloud_warehouse_client、file_upload_client、kingdee_service、db_to_xlsx（RPA）、xlsx 解析器 |
| `input/` | RPA 导出的输入数据（`销售单查询.xlsx`） |
| `interfaces/` | FastAPI app + `static/` 前端（index.html、login.html、app.js、app.css） |
| `outputs/` | 运行产物：task_runs、exception_orders、pushed_orders、execution_logs、scheduler_state、supplier_mappings、order_files |
| `scripts/` | 工具脚本：csv_to_xlsx、manual_push_group |
| `shared/` | 共享工具：`logging/logger.py`（JSON 日志 + 自动脱敏）、`env.py`（环境感知配置路径） |
| `tests/` | 测试（36 个文件，unittest 框架） |

---

## 配置系统

### 配置文件

- `config/config.json` — 默认配置
- `config/config.dev.json` — 开发环境
- `config/config_prod.json` — 生产环境（不提交 git）
- 环境选择：`APP_ENV` 环境变量 → `shared/env.py` 的 `resolve_config_path()` 加载对应文件

### 配置数据类（`application/config_service.py`）

| 数据类 | 关键字段 |
|---|---|
| `AppConfig` | 顶层配置，包含所有子配置 |
| `TaskConfig` | `name`、`window_minutes` |
| `ScheduleConfig` | `enabled`、`run_at`（HH:MM）、`schedule_id`、`name`、`check_interval_seconds` |
| `OrderSourceConfig` | `mode`：`mock` 或 `jikeyun` |
| `JikeyunConfig` | `api_url`、`app_key_env`、`app_secret_env`、`version`、`content_type`、`page_size`、分页参数 |
| `RpaConfig` | `enabled`、`xlsx_path` |
| `KingdeeConfig` | `enabled`、`mode`（mock/http）、`api_url`、`token_env`、`timeout_seconds` |
| `QixinConfig` | `mode`（mock/qixin）、`api_base_url`、`caller_id`、`secret_key_env`、`push_mode`（file/link） |
| `RuleConfig` | 所有规则开关和数据：`excluded_warehouses`、`excluded_skus`、`restricted_regions`、`sku_group_map`、`personal_order_filter`、`order_prefix_filter`、`special_skus` |
| `MessageConfig` | `max_attempts`、`retry_interval_seconds` |
| `OutputConfig` | `order_file_dir` |
| `DownloadConfig` | `base_url`、`secret_key_env`、`file_url` |
| `UploadConfig` | `enabled`、`api_url`、`timeout_seconds` |

### 配置热更新

- 配置在每次 API 请求和调度 tick 时重新加载
- `PUT /config` 立即生效
- `PUT /config/rules` 局部更新规则字段（白名单：`RULE_UPDATE_KEYS`）
- SKU-群映射、区域限发、排除 SKU 支持 XLSX 批量导入

---

## 环境变量

| 变量 | 用途 | 默认值 |
|---|---|---|
| `APP_ENV` | 环境标识（dev/prod） | `dev` |
| `JIKEYUN_APPKEY` | 吉客云 AppKey | 必填（jikeyun 模式） |
| `JIKEYUN_APP_SECRET` | 吉客云 AppSecret | 必填（jikeyun 模式） |
| `DOWNLOAD_SECRET_KEY` | 文件下载签名密钥 | 必填 |
| `KINGDEE_TOKEN` | 金蝶 API token | kingdee 启用时必填 |
| `AI_DDTS_ADMIN_PASSWORD` | 管理后台密码 | 空（不启用认证） |
| `AI_DDTS_ADMIN_USER` | 管理后台用户名 | `admin` |
| `AI_DDTS_SESSION_SECRET` | Session cookie 签名密钥 | 回退到 admin 密码 |
| `PORT` | 服务端口 | `9000` |

密钥通过 `.env` 文件管理，禁止提交到 git。

---

## 规则系统

### 规则执行顺序

`CustomerTypeRule → OrderPrefixRule → WarehouseRule → SkuServiceRule → RegionRule → GroupRule`

### RuleDecision 三态

- `PASS` → 通过，进入下一规则
- `IGNORE` → 静默忽略，不进异常（如排除仓库）
- `ERROR` → 进异常订单列表（如区域限发）

### 规则列表

| 规则 | 文件 | 行为 |
|---|---|---|
| `CustomerTypeRule` | `domain/rules/customer_type_rule.py` | 忽略 `-MULTI` 后缀订单（个人顾客） |
| `OrderPrefixRule` | `domain/rules/order_prefix_rule.py` | 忽略不在白名单前缀的订单 |
| `WarehouseRule` | `domain/rules/warehouse_rule.py` | 忽略排除仓库的订单 |
| `SkuServiceRule` | `domain/rules/sku_rule.py` | 忽略排除 SKU 的订单 |
| `RegionRule` | `domain/rules/region_rule.py` | SKU+区域匹配 → ERROR（限发） |
| `GroupRule` | `domain/rules/group_rule.py` | SKU 无配置推送群 → ERROR |
| `SupplierRule` | `domain/rules/supplier_rule.py` | PASS-through，供应商映射可见性 |
| `SpecialSkuRule` | `domain/rules/special_sku_rule.py` | 临时推送正选白名单 |

### 新增规则

1. 继承 `OrderRule`，实现 `evaluate(context) -> RuleResult`
2. 在 `domain/rules/` 下创建文件
3. 在 `manual_runner.py` 的 `build_pipeline_from_config()` 中注册
4. 测试必须覆盖 PASS / IGNORE / ERROR 三种决策

---

## 状态与枚举（强制）

**所有状态必须使用 Enum，禁止魔法字符串。**

| 枚举 | 文件 | 值 |
|---|---|---|
| `RuleDecision` | `domain/enums/rule.py` | `PASS`、`IGNORE`、`ERROR` |
| `PushStatus` | `domain/enums/status.py` | `PENDING`、`SUCCESS`、`PARTIAL`、`FAILED` |
| `PaymentStatus` | `domain/enums/status.py` | `UNPAID`、`PAID` |
| `KingdeeStatus` | `domain/enums/status.py` | `DISABLED`、`PENDING`、`SUCCESS`、`FAILED` |
| `SchedulerStatus` | `domain/enums/status.py` | `DISABLED`、`NOT_DUE`、`ALREADY_RAN`、`RAN` |
| `ExecutionLogStage` | `domain/enums/execution_log.py` | `TASK`、`FETCH`、`RULE`、`FILE`、`MESSAGE`、`KINGDEE`、`RECEIPT`、`TEMP_PUSH` |
| `ExecutionLogResult` | `domain/enums/execution_log.py` | `SUCCESS`、`FAILED`、`SKIPPED`、`PARTIAL` |
| `ExceptionProcessStatus` | `domain/enums/exception.py` | `PENDING`、`PROCESSED` |

---

## 日志与安全（强制）

1. **所有核心流程必须记录日志**（`log_info` / `log_error`）
2. **所有日志必须包含 `trace_id`**（通过 `TaskContext` 传递）
3. **禁止使用 `print`**
4. **禁止记录敏感信息**（APP_SECRET / token / 密码）
5. 日志模块：`shared/logging/logger.py`，JSON 结构化日志，自动脱敏（`sanitize_payload()` 递归脱敏 `secret`、`token`、`password`、`sign` 等字段）

---

## 前端时区陷阱（强制）

**禁止在前端用 `toISOString()` 把 datetime-local 输入转为 ISO 字符串传给后端。**

`toISOString()` 会把本地时间转为 UTC，导致时区偏移（如 UTC+8 下 16:15 变成 08:15）。

```javascript
// 错误 ❌
const iso = new Date("2026-05-27T16:15:00").toISOString();
// → "2026-05-27T08:15:00.000Z"（UTC，偏移了8小时）

// 正确 ✅
function toLocalIso(value) {
  const d = new Date(value);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
const iso = toLocalIso("2026-05-27T16:15:00");
// → "2026-05-27T16:15:00"（保留本地时间）
```

规则：
1. datetime-local → 后端：用 `toLocalIso()` 保留本地时间
2. 后端 ISO → 前端显示：用 `new Date(iso)` 解析后格式化（`getHours()` 等方法自动按本地时区）
3. 跨时区场景（如日志导出）才用 `toISOString()`

---

## 代码修改规范（强制）

修改已有代码必须标记注释块：

```python
# === MODIFIED START ===
# 原因：简述为什么改
# 影响范围：改了哪些模块/功能
# === MODIFIED END ===
```

新增文件不需要此标记。

---

## 设计模式

### 数据类

- 所有值对象使用 `@dataclass(frozen=True, slots=True)`
- 禁止可变默认参数（`tuple` 而非 `list` 作为默认值）

### 依赖注入

- 通过 Protocol 类和 Callable 注入依赖
- `Pipeline` 接受 `MessageSender`、`KingdeeService` 等 Protocol 接口
- 基础设施客户端接受可选 `urlopen`、`clock` 等 callable 用于测试注入
- 常用 Callable 类型：`Transport`、`Clock`、`RpaExporter`、`Sender`、`LogInfo`、`LogError`

### Mock/Real 模式切换

每个外部集成都支持 mock 模式（测试）和 real 模式（生产），通过 config 切换：
- `source.mode`：`mock` / `jikeyun`
- `qixin.mode`：`mock` / `qixin`
- `kingdee.mode`：`mock` / `http`

### 持久化

所有 store 使用 JSON 文件存储在 `outputs/` 下：
- `TaskRunStore`、`ExceptionOrderStore`、`PushedOrderStore`、`ExecutionLogStore`、`PaymentReceiptStore`、`SchedulerStateStore`、`SupplierMappingStore`、`SpecialPushOrderStore`

---

## 定时调度

1. 支持多定时任务，配置在 `config.json` 的 `schedules` 数组
2. 每条 schedule 独立记录运行状态（`schedule_id` 区分）
3. 运行窗口逻辑：
   - 首次：`昨天 run_at → 今天 run_at`
   - 后续：`上次 run_at → 本次 run_at`（无缝衔接）
4. 后台循环：`application/scheduler_loop.py`，asyncio 驱动
5. 状态持久化：`outputs/scheduler_state.json`

---

## 外部系统集成

| 系统 | 客户端 | 用途 |
|---|---|---|
| 吉客云 | `infrastructure/jikeyun_client.py` | 订单拉取（OpenAPI + HMAC-MD5 签名 + 分页 + 重试） |
| 祺信 | `infrastructure/qixin_client.py` | 企业微信群消息/文件推送（HMAC-SHA256 签名） |
| 金蝶 | `infrastructure/kingdee_service.py` | 采购单提交 |
| 云仓 | `infrastructure/cloud_warehouse_client.py` | 供应商数据同步 |
| 文件服务 | `infrastructure/file_upload_client.py` | Excel 文件上传托管 |
| RPA | `infrastructure/db_to_xlsx.py` | PyAutoGUI 桌面导出自动化（坐标硬编码，Flutter 应用） |

---

## API 端点

### 任务

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/tasks/run` | 运行任务（配置源） |
| POST | `/tasks/mock-run` | 运行任务（mock 模式） |
| POST | `/tasks/{trace_id}/repush` | 重跑任务 |
| GET | `/tasks/latest` | 最新任务摘要 |
| GET | `/tasks/history` | 任务历史 |

### 临时推送

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/temp-push/run` | 运行临时推送 |
| GET | `/temp-push/orders` | 列出临时推送记录 |
| GET | `/temp-push/{id}/orders/download` | 下载临时推送订单 CSV |

### 配置

| 方法 | 路径 | 用途 |
|---|---|---|
| GET/PUT | `/config` | 查看/更新完整配置 |
| PUT | `/config/rules` | 局部更新规则 |
| PUT | `/config/rpa` | 切换 RPA 开关 |
| POST | `/config/regions/upload-xlsx` | 预览区域 XLSX 导入 |
| POST | `/config/regions/confirm` | 确认区域导入 |
| POST | `/config/sku-groups/upload-xlsx` | 预览 SKU 群 XLSX 导入 |
| POST | `/config/sku-groups/confirm` | 确认 SKU 群导入 |

### 查询与导出

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/exception-orders` | 异常订单列表 |
| GET | `/exception-orders/download` | 下载异常订单 CSV |
| GET | `/execution-logs` | 执行日志列表 |
| GET | `/execution-logs/download` | 下载执行日志 CSV |
| GET | `/supplier-mappings` | SKU-供应商映射 |
| GET | `/order-files/download` | 签名文件下载 |

### 调度器

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/scheduler/status` | 调度器状态 |
| POST | `/scheduler/tick` | 触发调度 tick |
| GET | `/scheduler/loop/status` | 后台循环状态 |
| PUT | `/scheduler/state` | 强制更新调度器状态 |

### 认证

- 可选 cookie-based 管理员认证（`ADMIN_SESSION_COOKIE`）
- 豁免路径：`/health`、`/login`、`/logout`、`/order-files/download`
- HMAC-SHA256 签名 session token

---

## 测试

### 框架

- `unittest`（标准库）
- 36 个测试文件在 `tests/` 下

### 运行测试

```bash
uv run python -m pytest tests/ -v                    # 全部
uv run python -m pytest tests/test_xxx.py -v         # 单个文件
uv run python -m pytest tests/test_xxx.py::test_func -v  # 单个用例
```

### 测试模式

- `setUp()` 创建隔离的临时文件在 `tmp/`
- 网络调用用 `_block_network` 阻断
- 自定义 mock：`RecordingMessageSender`、`RecordingKingdeeService`、`FailingMessageSender`、`PartiallyFailingMessageSender`
- 通过构造函数注入依赖（如 `ApiService(config_path=..., task_store_path=...)`）

---

## 运行产物（`outputs/`）

| 文件 | 内容 |
|---|---|
| `task_runs.json` | 任务运行记录 |
| `exception_orders.json` | 异常订单 |
| `pushed_orders.json` | 已推送订单 |
| `execution_logs.json` | 执行日志 |
| `scheduler_state.json` | 调度器状态 |
| `sku_supplier_mappings.json` | SKU-供应商映射 |
| `payment_receipts.json` | 付款回执 |
| `order_files/` | 生成的 Excel 文件 |
| `special_push/` | 临时推送产物 |

---

## 部署

- **本地 Windows**：`uv run uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory`
- **Windows 服务**：通过 `nssm` 托管
- **Linux 服务器**：systemd 或 nohup
- 必须使用 `--factory` 标志（app 使用工厂模式）
- `config_prod.json` 不提交 git，服务器本地维护
