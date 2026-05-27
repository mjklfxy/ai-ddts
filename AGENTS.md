# 开发规范（强制）

## 一、架构约束

1. **分层架构**：domain → application → infrastructure → interfaces，依赖只能单向向下
2. **domain 层不得依赖 infrastructure 层**（纯业务规则，不引用外部 API）
3. **pipeline.py 只编排流程**，不含业务逻辑
4. **interfaces/app.py 只做路由**，不含业务逻辑
5. **所有业务规则必须继承 OrderRule**，放在 `domain/rules/` 下

---

## 二、规则系统

1. 规则必须返回 `RuleResult(decision, rule_name, reason)`
2. `RuleDecision` 三态：
   - `PASS` → 进入下一规则
   - `IGNORE` → 静默忽略，不进异常（如 WarehouseRule）
   - `ERROR` → 进异常订单列表
3. 新增规则：继承 `OrderRule`，实现 `evaluate(context) -> RuleResult`，在 `domain/rules/` 下创建文件
4. 规则注册：在 `domain/rule_engine.py` 的 `create_default_engine()` 中添加

---

## 三、状态与枚举

1. **所有状态必须使用 Enum**（禁止魔法字符串）
2. 枚举定义在 `domain/enums/` 下：
   - `rule.py` → `RuleDecision`
   - `status.py` → `PushStatus` / `PaymentStatus` / `KingdeeStatus` / `SchedulerStatus`
   - `execution_log.py` → `ExecutionLogStage` / `ExecutionLogResult`
   - `exception.py` → `ExceptionProcessStatus`

---

## 四、日志与安全

1. **所有核心流程必须记录日志**（`log_info` / `log_error`）
2. **所有日志必须包含 `trace_id`**（通过 `TaskContext` 传递）
3. **禁止使用 `print`**
4. **禁止记录敏感信息**（APP_SECRET / token / 密码）
5. 日志模块在 `shared/logging/logger.py`，自动脱敏

---

## 五、配置管理

1. 全局配置在 `config/config.{env}.json`，通过 `application/config_service.py` 加载
2. 环境通过 `APP_ENV` 环境变量控制（dev/prod），决定读取 `config.dev.json` 或 `config.prod.json`，默认 `dev`
3. 密钥通过 `.env` 文件管理，禁止提交到 git
4. `config.prod.json` 不提交到 git，由服务器本地维护
5. 配置数据类：`AppConfig` / `TaskConfig` / `ScheduleConfig` 等
6. 运行时配置更新通过 `PUT /config` API，立即生效
7. SKU-群映射、区域限发、排除 SKU 支持 XLSX 批量导入

---

## 六、代码修改规范

修改已有代码必须标记注释块：

```python
# === MODIFIED START ===
# 原因：
# 影响范围：
# === MODIFIED END ===
```

---

## 七、测试

1. 测试文件放在 `tests/` 下，文件名 `test_<模块>.py`
2. 使用 `unittest` 框架
3. 运行测试：
   ```bash
   .venv/Scripts/python.exe -m unittest discover tests -v
   ```
4. 规则测试必须覆盖 PASS / IGNORE / ERROR 三种决策

---

## 八、数据持久化

运行产物存放在 `outputs/` 目录：

| 文件 | 内容 |
|---|---|
| `task_runs.json` | 任务运行记录 |
| `exception_orders.json` | 异常订单记录 |
| `pushed_orders.json` | 已推送订单记录 |
| `execution_logs.json` | 执行日志 |
| `scheduler_state.json` | 调度器运行状态 |
| `sku_supplier_mappings.json` | SKU-供应商映射 |
| `payment_receipts.json` | 付款回执 |
| `order_files/` | 生成的 CSV 文件 |
| `*_exports/` | 导出的 CSV 文件 |

---

## 九、外部系统集成

| 系统 | 客户端 | 用途 |
|---|---|---|
| 吉客云 | `infrastructure/jikeyun_client.py` | 订单拉取（OpenAPI + 签名 + 分页 + 重试） |
| 祺信 | `infrastructure/qixin_client.py` | 企业微信群消息/文件推送 |
| 金蝶 | `infrastructure/kingdee_service.py` | 采购单提交（当前未启用） |
| 云仓 | `infrastructure/cloud_warehouse_client.py` | 供应商数据同步 |
| 公网文件服务 | `infrastructure/file_upload_client.py` | CSV 文件上传托管 |
| RPA | `infrastructure/db_to_xlsx.py` | PyAutoGUI 桌面导出自动化 |

---

## 十、定时调度

1. 支持多定时任务，配置在 `config.json` 的 `schedules` 数组
2. 每条 schedule 独立记录运行状态（`schedule_id` 区分）
3. 运行窗口逻辑：
   - 首次：`昨天 run_at → 今天 run_at`
   - 后续：`上次 run_at → 本次 run_at`（无缝衔接）
4. 后台循环在 `application/scheduler_loop.py`，asyncio 驱动
