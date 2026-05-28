# AI-DDTS — 订单自动分发推送系统

## 0. 项目背景

公司电商业务通过吉客云（JackYun）管理销售订单。日常运营中，不同品类的订单需要分发到对应的企业微信业务群（如"无抗蛋订货群"、"小麻花订货群"等），由群内负责人跟进发货。

**此前的痛点：**
- 运营人员需要手动从吉客云导出订单，再逐个群发送，每天重复且耗时
- 手动操作容易遗漏订单或发错群
- 订单量增长后，人工分发成为瓶颈

**本系统的解决方案：**
- 通过吉客云开放 API 自动拉取订单，替代手动导出
- 内置规则引擎自动过滤无效订单（排除仓库、排除 SKU、区域限发等），减少人工审核
- 按 SKU 自动匹配目标群，生成 CSV 并推送到对应企业微信群
- 支持定时调度，每天固定时间自动执行，无需人工干预
- 异常订单自动记录，运营只需关注异常处理

**涉及的外部系统：**
- **吉客云（JackYun）**— 电商 ERP，订单数据源，通过 OpenAPI 拉取销售单
- **祺信（Qixin）**— 企业微信消息推送服务，通过 API 向群发送消息/文件
- **金蝶（Kingdee）**— 财务系统，可选自动提交采购申请单（当前未启用）
- **云仓**— 供应商数据同步，用于 SKU-供应商映射

---

## 1. 项目概述

AI-DDTS 是一个订单自动处理流水线，将吉客云（Jikeyun/JackYun）电商平台的销售单自动分发到企业微信各业务群。

**核心流程：**
```
吉客云 OpenAPI 拉单
    ↓
规则引擎过滤（仓库/SKU/区域/客户类型）
    ↓
按业务群拆分订单
    ↓
生成 CSV 文件
    ↓
上传至公网文件服务器
    ↓
通过祺信（Qixin）API 推送到企业微信群
```

**端到端已跑通。** 吉客云拉单 → 规则过滤 → 拆分 → CSV → 上传 → 推群，全链路验证通过。

---

## 2. 环境准备

### 依赖

项目使用 **uv** 管理 Python 依赖（`uv.lock` / `uv.toml`），Python 3.13+。

```bash
# 安装 uv（如未安装）
pip install uv

# 安装依赖
uv sync
```

### 环境变量

在项目根目录创建 `.env` 文件（参考 `.env.example`）：

| 变量名 | 说明 | 默认值 |
|---|---|---|
| `APP_ENV` | 环境标识（dev/prod） | `dev` |
| `JIKEYUN_APPKEY` | 吉客云开放平台 AppKey | 无 |
| `JIKEYUN_APP_SECRET` | 吉客云开放平台 AppSecret | 无 |
| `DOWNLOAD_SECRET_KEY` | 文件下载链接签名密钥 | 无 |
| `ADMIN_PASSWORD` | 管理后台密码 | `changeme` |

**设置方式：** 在项目根目录创建 `.env` 文件或系统环境变量。

---

## 3. 启动

```bash
cd C:\Users\666\projects\AI-DDTS

# 开发环境（默认，mock 模式，调度关闭）
uv run uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory

# 生产环境
$env:APP_ENV="prod"; uv run uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory
```

**必须加 `--factory`**，因为 `interfaces/app.py` 通过 `create_app()` 函数返回 FastAPI 实例，没有全局 app 变量。

启动后访问 `http://localhost:8000` 进入管理后台。页面左下角会显示当前环境标识（DEV / PROD）。

---

## 4. 部署

### 4.1 本机部署（当前方式）

当前项目直接在 Windows 本机运行，通过 PowerShell 启动 uvicorn：

```powershell
cd C:\Users\666\projects\AI-DDTS
$env:JIKEYUN_APPKEY="your_appkey"
$env:JIKEYUN_APP_SECRET="your_secret"
$env:DOWNLOAD_SECRET_KEY="your_download_key"

uv run uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory
```

关掉终端服务就停。如需后台常驻，可用以下方式：

**方式一：PowerShell 后台启动**
```powershell
Start-Process -NoNewWindow python -ArgumentList "-m uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory"
```

**方式二：nssm 注册为 Windows 服务（推荐生产环境）**
```powershell
# 安装 nssm（如未安装）
scoop install nssm

# 注册服务
nssm install AI-DDTS "C:\Users\666\projects\AI-DDTS\.venv\Scripts\python.exe"
nssm set AI-DDTS AppParameters "-m uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory"
nssm set AI-DDTS AppDirectory "C:\Users\666\projects\AI-DDTS"
nssm set AI-DDTS AppEnvironmentExtra "JIKEYUN_APPKEY=xxx" "JIKEYUN_APP_SECRET=xxx" "DOWNLOAD_SECRET_KEY=xxx"
nssm set AI-DDTS Start SERVICE_AUTO_START

# 启动
nssm start AI-DDTS

# 管理
nssm status AI-DDTS
nssm stop AI-DDTS
nssm remove AI-DDTS confirm
```

### 4.2 服务器部署（Linux）

```bash
# 克隆代码
git clone <repo-url> /opt/AI-DDTS
cd /opt/AI-DDTS

# 安装依赖
uv sync

# 设置环境变量
export JIKEYUN_APPKEY="your_appkey"
export JIKEYUN_APP_SECRET="your_secret"
export DOWNLOAD_SECRET_KEY="your_download_key"

# 启动
nohup uv run uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory &

# 或用 systemd 管理
# 创建 /etc/systemd/system/ai-ddts.service：
```

```ini
[Unit]
Description=AI-DDTS Order Distribution Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/AI-DDTS
Environment=JIKEYUN_APPKEY=xxx
Environment=JIKEYUN_APP_SECRET=xxx
Environment=DOWNLOAD_SECRET_KEY=xxx
ExecStart=/opt/AI-DDTS/.venv/bin/python -m uvicorn interfaces.app:create_app --host 0.0.0.0 --port 8000 --factory
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-ddts
sudo systemctl start ai-ddts
sudo systemctl status ai-ddts
```

### 4.3 部署检查清单

部署后确认以下内容正常：

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 调度器循环是否运行
curl http://localhost:8000/scheduler/loop/status
# 确认 "running": true

# 3. 环境变量是否加载
curl http://localhost:8000/config
# 检查 jikeyun 配置是否正确

# 4. 手动触发一次测试
curl -X POST http://localhost:8000/tasks/mock-run
# 确认返回 passed_count > 0

# 5. 配套服务连通性
curl http://mengyang.renruikeji.cn/api/userid -X POST -H "Content-Type: application/json" -d '{"mobile":"18231132648"}'
```

### 4.4 注意事项

- **环境变量需持久化**：PowerShell 的 `$env:` 只在当前终端有效，生产环境用 nssm/systemd 设置
- **端口冲突**：确保 8000 端口未被占用，或改为其他端口
- **配套服务依赖**：订单推送依赖 `:243` 服务器上的文件上传和 userid 解析服务，部署前确认该服务正常
- **日志排查**：出问题看 uvicorn 终端输出，所有错误都带 `trace_id`

---

## 5. 项目结构

```
AI-DDTS/
├── main.py                          # CLI 入口（当前未使用，功能走 Web）
├── AGENTS.md                        # 开发规范（架构约束、代码风格）
├── config/
│   └── config.json                  # 全局配置（规则、调度、外部服务等）
├── application/                     # 应用层 — 流程编排，不含业务逻辑
│   ├── manual_runner.py             # run_once() 核心运行入口
│   ├── pipeline.py                  # Pipeline：规则→拆分→生成→上传→推送
│   ├── scheduler.py                 # 定时调度器（DailyFixedTimeScheduler）
│   ├── scheduler_loop.py            # 后台 asyncio 调度循环
│   ├── config_service.py            # 配置加载与数据类（AppConfig 等）
│   ├── api_service.py               # ApiService：所有 API 业务逻辑
│   ├── task_service.py              # TaskContext 创建
│   ├── task_code.py                 # 批次号生成（yyyyMMdd + 4位序号）
│   ├── order_splitter.py            # 按群分组拆单
│   ├── file_generator.py            # CSV 文件生成
│   ├── sku_group_map.py             # SKU-群映射 CRUD
│   ├── task_run_store.py            # 任务运行记录持久化
│   ├── exception_order_store.py     # 异常订单持久化/导出
│   ├── pushed_order_store.py        # 已推送订单持久化/导出
│   ├── execution_log_store.py       # 执行日志持久化/导出
│   ├── payment_receipt_store.py     # 付款回执管理
│   ├── supplier_mapping_store.py    # SKU-供应商映射持久化
│   └── xlsx_reader.py               # XLSX 读取（地址兜底）
├── domain/                          # 领域层 — 纯业务规则
│   ├── rule_engine.py               # 规则引擎（顺序执行各规则）
│   ├── exception_order.py           # 异常订单模型
│   ├── sku_group_info.py            # SKU 群组信息
│   ├── supplier.py                  # 供应商信息
│   ├── enums/
│   │   ├── rule.py                  # RuleDecision: PASS/IGNORE/ERROR
│   │   ├── status.py                # PushStatus/PaymentStatus/KingdeeStatus/SchedulerStatus
│   │   ├── execution_log.py         # ExecutionLogStage/ExecutionLogResult
│   │   └── exception.py             # ExceptionProcessStatus
│   └── rules/
│       ├── base.py                  # OrderRule ABC + RuleContext + RuleResult
│       ├── warehouse_rule.py        # 排除仓库 → IGNORE
│       ├── sku_rule.py              # 排除 SKU → ERROR
│       ├── region_rule.py           # 区域限发 → ERROR
│       ├── group_rule.py            # 未配置群 → ERROR
│       ├── customer_type_rule.py    # 个人客户过滤（-MULTI 后缀）
│       ├── order_prefix_rule.py     # 订单前缀白名单
│       └── supplier_rule.py         # SKU-供应商映射（PASS，仅记录映射关系）
├── infrastructure/                  # 基础设施层 — 外部 API 适配
│   ├── jikeyun_client.py            # 吉客云 OpenAPI 客户端（分页、签名、重试）
│   ├── qixin_client.py              # 祺信 API 客户端（文本推送/文件直推）
│   ├── file_upload_client.py        # 文件上传至公网服务器
│   ├── message_adapter.py           # 消息发送重试适配器
│   ├── cloud_warehouse_client.py    # 云仓 API（供应商同步）
│   ├── product_caller_sync_client.py # 配置同步客户端
│   ├── kingdee_service.py           # 金蝶采购单提交
│   ├── db_to_xlsx.py                # RPA：PyAutoGUI 桌面导出自动化
│   ├── xlsx_region_parser.py        # 区域限发 XLSX 解析
│   ├── xlsx_sku_group_parser.py     # SKU 群组 XLSX 解析
│   └── xlsx_sku_parser.py           # 排除 SKU XLSX 解析
├── interfaces/                      # 接口层
│   ├── app.py                       # FastAPI 应用（所有路由）
│   └── static/                      # 前端静态文件（HTML/JS/CSS）
├── shared/
│   └── logging/
│       └── logger.py                # JSON 日志（自动脱敏）
├── tests/                           # 测试（unittest）
├── outputs/                         # 运行产物
│   ├── task_runs.json               # 任务运行记录
│   ├── exception_orders.json        # 异常订单记录
│   ├── pushed_orders.json           # 已推送订单记录
│   ├── execution_logs.json          # 执行日志
│   ├── scheduler_state.json         # 调度器状态（今日是否已运行）
│   ├── sku_supplier_mappings.json   # SKU-供应商映射缓存
│   ├── order_files/                  # 生成的 CSV 文件
│   └── *_exports/                   # 导出的 CSV 文件
└── input/
    └── 销售单查询.xlsx               # 吉客云桌面导出（地址兜底）
```

---

## 6. 配置说明（config/config.json）

### 5.1 任务配置

```json
"task": {
  "name": "daily-direct-order",
  "window_minutes": 1440        // 手动模式的拉单窗口（分钟），1440 = 24小时
}
```

### 5.2 定时调度

```json
"schedules": [
  {
    "schedule_id": "default",       // 唯一标识，用于持久化运行状态
    "name": "默认定时任务",
    "enabled": true,                // false = 不触发
    "run_at": "17:00",              // 每天触发时间（HH:MM 24小时制）
    "check_interval_seconds": 60    // 后台 loop 检查间隔（秒）
  }
]
```

- 支持多条定时任务，每条独立记录运行状态
- 首次运行窗口：`昨天 run_at → 今天 run_at`（24 小时兜底）
- 后续运行窗口：`上次 run_at → 本次 run_at`（动态窗口，不重叠不漏单）
- 状态持久化在 `outputs/scheduler_state.json`

### 5.3 订单来源

```json
"source": {
  "mode": "jikeyun"     // "jikeyun" = 真实吉客云, "mock" = 测试数据
}
```

测试时改为 `"mock"`，使用内置测试订单验证流程。

### 5.4 RPA 配置

```json
"rpa": {
  "enabled": true,
  "xlsx_path": "input\\销售单查询.xlsx"
}
```

RPA 通过 PyAutoGUI 从吉客云桌面端自动导出收件人地址/电话，作为 API 拉单的补充数据源。`enabled: true` 时自动读取 XLSX 补充地址信息。

### 5.5 推送模式

```json
"qixin": {
  "push_mode": "file"   // "file" = 直推文件, "link" = 推文本+下载链接
}
```

### 5.6 SKU-群映射

`rules.sku_group_map` 是核心配置，决定每个 SKU 推送到哪个企业微信群：

```json
"sku_group_map": {
  "某SKU名称": {
    "group_name": "群名称",
    "owner_mobile": "负责人手机号",
    "user_id": ""              // 留空，推送时自动通过手机号解析
  }
}
```

**重要：** SKU 名称必须与吉客云 API 返回的 `goodsName` / `skuName` **完全一致**（包括标点、空格、特殊字符）。不匹配的 SKU 会被 GroupRule 拦截，报"未配置推送群"。

可通过 Web 后台或直接编辑 config.json 维护。也可以通过 API 上传 XLSX 批量导入（`POST /config/sku-groups/upload-xlsx`）。

**排查 SKU 匹配问题：** 查看 `outputs/exception_orders.json`，筛选 `reason` 包含"未配置"的记录，提取其中的 `sku_code` 字段，就是缺失的 SKU。

### 5.7 其他规则

| 配置项 | 说明 |
|---|---|
| `rules.excluded_warehouses` | 排除仓库列表（命中 → 忽略，不进异常） |
| `rules.excluded_skus` | 排除 SKU 列表（命中 → 异常） |
| `rules.restricted_regions` | 区域限发（SKU + 省/市/区 → 异常） |
| `rules.allowed_order_prefixes` | 订单前缀白名单 |

---

## 7. 规则引擎

订单按顺序经过以下规则过滤：

```
CustomerTypeRule  → 个人客户过滤（-MULTI 后缀订单忽略）
OrderPrefixRule   → 订单前缀白名单
WarehouseRule     → 排除仓库 → IGNORE（不进异常）
SkuServiceRule    → 排除 SKU → ERROR（进异常）
RegionRule        → 区域限发 → ERROR（进异常）
GroupRule         → 未配置群 → ERROR（进异常）
```

**规则结果：**
- `PASS` → 进入下一规则
- `IGNORE` → 忽略，不进异常
- `ERROR` → 进异常订单列表

所有业务规则必须继承 `OrderRule`，在 `domain/rules/` 下实现。

---

## 8. 定时调度系统

### 架构

```
BackgroundSchedulerLoop（asyncio 后台循环）
  → 每 N 秒调用 tick_callback
    → ApiService.tick_scheduler()
      → DailyFixedTimeScheduler.tick_many(schedules)
        → tick(schedule) × 每条配置
          → _run_configured_task(schedule)
            → run_once(...)
```

### 运行窗口逻辑

- **首次运行 / 手动触发：** `now - 24h → now`
- **定时首次：** `昨天 run_at → 今天 run_at`
- **定时后续：** `上次 run_at → 本次 run_at`（无缝衔接，不重叠）

### 状态

查询调度器状态：
```
GET /scheduler/status
GET /scheduler/loop/status
POST /scheduler/tick          # 手动触发一次 tick
```

---

## 9. API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET/POST | `/login` | 管理员登录页 |
| GET | `/logout` | 退出登录 |
| GET | `/config` | 查看配置 |
| PUT | `/config` | 更新配置 |
| PUT | `/config/rules` | 更新规则配置 |
| POST | `/config/regions/upload-xlsx` | 上传区域限发 XLSX |
| POST | `/config/sku-groups/upload-xlsx` | 上传 SKU 群组 XLSX |
| POST | `/config/sku-groups/sync-caller-configs` | 同步配置到祺信 |
| POST | `/config/excluded-skus/upload-xlsx` | 上传排除 SKU XLSX |
| GET | `/supplier-mappings` | 供应商映射列表 |
| PUT | `/supplier-mappings` | 更新供应商映射 |
| GET | `/exception-orders` | 异常订单列表 |
| GET | `/exception-orders/download` | 异常订单 CSV 导出 |
| GET | `/execution-logs` | 执行日志列表 |
| GET | `/execution-logs/download` | 执行日志 CSV 导出 |
| GET | `/tasks/run` | 手动触发任务 |
| POST | `/tasks/mock-run` | mock 模式触发任务 |
| GET | `/tasks/latest` | 最新任务摘要 |
| GET | `/tasks/history` | 任务历史记录 |
| GET | `/tasks/{trace_id}/pushed-orders/download` | 已推送订单 CSV 导出 |
| GET | `/tasks/{trace_id}/payment` | 查看付款信息 |
| POST | `/tasks/{trace_id}/payment-receipt` | 上传付款回执 |
| GET | `/order-files/download` | 下载订单文件 |
| GET | `/scheduler/status` | 调度器状态 |
| POST | `/scheduler/tick` | 手动触发调度 tick |
| GET | `/scheduler/loop/status` | 后台循环状态 |

---

## 10. 配套服务

订单文件需上传到公网服务器（`xxx.xxx.x.243:8088`），该服务提供：

1. **手机号 → userid 解析：** `POST /api/userid`，参数 `{"mobile": "..."}`
2. **文件托管：** `POST /api/files/upload`，`GET /api/files/{uuid}.csv`

服务已通过 tmux 运行在服务器上，会话名 `wuliu`。

服务器所需环境变量：`ODPS_ACCESS_ID`、`ODPS_SECRET_KEY`。

---

## 11. 吉客云收件人信息

目前通过 **PyAutoGUI 鼠标模拟** 从吉客云桌面端导出收件人地址/电话（`infrastructure/db_to_xlsx.py`）。

**首次使用：**
1. 打开浏览器进入吉客云销售单查询页面
2. 手动下载一单，输入验证码完成验证
3. 之后脚本可自动操作

导出文件存放在 `input/销售单查询.xlsx`，作为地址信息的兜底来源。

---

## 12. 开发规范

详见 [AGENTS.md](AGENTS.md)，核心约束：

1. 业务规则必须继承 `OrderRule`，放在 `domain/rules/`
2. `pipeline.py` 只编排流程，不含业务逻辑
3. `interfaces/app.py` 只做路由，不含业务逻辑
4. `domain` 层不得依赖 `infrastructure` 层
5. 所有状态必须使用 Enum
6. 所有日志必须包含 `trace_id`，禁止 `print`
7. 修改已有代码必须标记 `MODIFIED START/END` 注释块

### 运行测试

```bash
.venv/Scripts/python.exe -m unittest discover tests -v
```

---

## 13. Dev 测试工具

`tools/` 目录存放本地辅助脚本，不纳入版本控制。

### 订单 Excel 拆分工具

dev 环境所有订单推到同一个测试群（12121），推送后用此脚本按生产群名拆分 Excel，方便与生产推送结果对比。

**目录结构：**
```
tools/dev-split/
├── split.py          # 拆分脚本
└── results/          # 拆分结果输出
```

**用法：**
```bash
# 1. 把推过去的 xlsx 文件放到 tools/dev-split/ 目录下
# 2. 运行拆分
python tools/dev-split/split.py 12121_20260528xxxxx.xlsx
# 3. 结果在 tools/dev-split/results/ 下，每个生产群一个文件
```

未匹配的行（SKU 不在生产配置中）会单独输出到 `results/_未匹配.xlsx`。

---

## 14. 常见问题

### Q: 推送失败，userid 解析有问题
优先检查 userid 是否正确。手机号 → userid 依赖远程 API，可能不稳定。手动触发 tick 后查看执行日志定位具体失败阶段。

### Q: 定时任务没有自动触发
检查 `/scheduler/loop/status`，确认 `running: true`。如果为 false，重启服务。

### Q: 如何切换推送模式
修改 `config.json` 中 `qixin.push_mode`：`"file"` = 直推文件，`"link"` = 推文本链接。

### Q: 如何测试
将 `source.mode` 改为 `"mock"`，用测试数据跑一遍流程，确认后再切回 `"jikeyun"`。

### Q: 清理运行状态
删除 `outputs/scheduler_state.json` 和 `outputs/task_runs.json` 中对应记录。清理后重启服务。

### Q: 跑出来 0 单通过，全部报"未配置推送群"
SKU 名称不匹配。用以下命令对比订单 SKU 和配置 SKU：
```bash
python -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('outputs/exception_orders.json') as f:
    data = json.load(f)
latest = [d for d in data if d.get('trace_id') == sorted(set(r['trace_id'] for r in data))[-1]]
skus = set(d['sku_code'] for d in latest if '未配置' in d.get('reason',''))
for s in sorted(skus): print(s)
"
```
拿到 SKU 列表后加到 `config.json` 的 `sku_group_map` 中。

### Q: 收件人信息全部显示"未提供"
吉客云 OpenAPI 不返回收件人地址/电话，依赖 RPA 从桌面端导出 XLSX 补充。确保：
1. RPA 导出在拉单之前完成（先跑 RPA，再跑任务）
2. XLSX 中的订单号与 API 返回的订单号一致
3. 如果 XLSX 被重新导出覆盖，历史订单的地址信息会丢失

### Q: 定时任务只跑了 17:00 的，没有跑其他时间的
检查 `config.json` 中 `schedules` 数组，确认所有定时任务都 `enabled: true`。每条 schedule 用独立的 `schedule_id` 记录运行状态，互不影响。
